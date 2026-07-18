from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path, PureWindowsPath
from typing import Iterable

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


CATALOG_COLUMNS = {
    "reference_id", "document_uid", "manufacturer", "model_name",
    "chassis_code", "engine_code", "transmission_code", "model_year",
    "title", "manual_type_original", "manual_type_normalized",
    "system_name", "section_path", "download_status", "source_url",
    "source_hash", "original_local_path", "resolved_local_path",
    "file_exists", "pdf_valid", "size_bytes", "sha256", "error",
}


def connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialise_database(connection: sqlite3.Connection, schema_path: Path) -> None:
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    connection.commit()


def as_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def resolve_catalog_path(archive_root: Path | None, original_path: str, resolved_path: str) -> str:
    if archive_root and original_path:
        relative = Path(*PureWindowsPath(original_path).parts)
        return str((archive_root / relative).resolve())
    return resolved_path


def import_catalog(
    connection: sqlite3.Connection,
    csv_path: Path,
    archive_root: Path | None,
) -> tuple[int, int]:
    inserted = 0
    updated = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = CATALOG_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Catalog is missing columns: {sorted(missing)}")

        for row in reader:
            resolved_path = resolve_catalog_path(
                archive_root,
                row["original_local_path"],
                row["resolved_local_path"],
            )
            file_exists = int(Path(resolved_path).is_file()) if resolved_path else 0

            existing = connection.execute(
                "SELECT id FROM documents WHERE reference_id = ?",
                (row["reference_id"],),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO documents (
                    reference_id, document_uid, manufacturer, model_name,
                    chassis_code, engine_code, transmission_code, model_year,
                    title, manual_type_original, manual_type_normalized,
                    system_name, section_path, download_status, source_url,
                    source_hash, original_local_path, resolved_local_path,
                    file_exists, pdf_valid, size_bytes, sha256, download_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(reference_id) DO UPDATE SET
                    document_uid = excluded.document_uid,
                    manufacturer = excluded.manufacturer,
                    model_name = excluded.model_name,
                    chassis_code = excluded.chassis_code,
                    engine_code = excluded.engine_code,
                    transmission_code = excluded.transmission_code,
                    model_year = excluded.model_year,
                    title = excluded.title,
                    manual_type_original = excluded.manual_type_original,
                    manual_type_normalized = excluded.manual_type_normalized,
                    system_name = excluded.system_name,
                    section_path = excluded.section_path,
                    download_status = excluded.download_status,
                    source_url = excluded.source_url,
                    source_hash = excluded.source_hash,
                    original_local_path = excluded.original_local_path,
                    resolved_local_path = excluded.resolved_local_path,
                    file_exists = excluded.file_exists,
                    pdf_valid = excluded.pdf_valid,
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    download_error = excluded.download_error
                """,
                (
                    row["reference_id"],
                    row["document_uid"],
                    row["manufacturer"],
                    row["model_name"],
                    row["chassis_code"],
                    row["engine_code"],
                    row["transmission_code"],
                    as_int(row["model_year"]),
                    row["title"],
                    row["manual_type_original"],
                    row["manual_type_normalized"],
                    row["system_name"],
                    row["section_path"],
                    row["download_status"],
                    row["source_url"],
                    row["source_hash"],
                    row["original_local_path"],
                    resolved_path,
                    file_exists,
                    as_int(row["pdf_valid"]),
                    as_int(row["size_bytes"]),
                    row["sha256"],
                    row["error"],
                ),
            )

            document_id = connection.execute(
                "SELECT id FROM documents WHERE reference_id = ?",
                (row["reference_id"],),
            ).fetchone()["id"]

            connection.execute(
                """
                INSERT INTO pdf_analysis(document_id, analysis_status)
                VALUES (?, 'pending')
                ON CONFLICT(document_id) DO NOTHING
                """,
                (document_id,),
            )

            inserted += int(existing is None)
            updated += int(existing is not None)

    connection.commit()
    return inserted, updated


def require_pymupdf() -> None:
    if fitz is None:
        print(
            "PyMuPDF is not installed.\n"
            "Install it with:\n\n"
            "  py -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(2)


def selected_documents(
    connection: sqlite3.Connection,
    limit: int | None,
    retry_errors: bool,
    reference_id: str | None,
) -> list[sqlite3.Row]:
    clauses = ["d.file_exists = 1"]
    values: list[object] = []

    if reference_id:
        clauses.append("d.reference_id = ?")
        values.append(reference_id)
    elif retry_errors:
        clauses.append("a.analysis_status IN ('pending', 'error')")
    else:
        clauses.append("a.analysis_status = 'pending'")

    sql = f"""
        SELECT d.*, a.analysis_status
        FROM documents d
        JOIN pdf_analysis a ON a.document_id = d.id
        WHERE {' AND '.join(clauses)}
        ORDER BY d.reference_id
    """

    if limit is not None:
        sql += " LIMIT ?"
        values.append(limit)

    return connection.execute(sql, values).fetchall()


def extract_document(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    store_text: bool,
    text_threshold: int,
) -> None:
    path = Path(row["resolved_local_path"])

    connection.execute(
        "UPDATE pdf_analysis SET analysis_status='processing' WHERE document_id=?",
        (row["id"],),
    )
    connection.commit()

    try:
        document = fitz.open(path)

        if document.needs_pass:
            connection.execute(
                """
                UPDATE pdf_analysis
                SET analysis_status='error', encrypted=1,
                    extraction_error='Encrypted PDF requires a password',
                    analyzed_at=CURRENT_TIMESTAMP
                WHERE document_id=?
                """,
                (row["id"],),
            )
            connection.commit()
            return

        metadata = document.metadata or {}
        toc = document.get_toc(simple=True) or []

        connection.execute(
            "DELETE FROM pdf_bookmarks WHERE document_id=?",
            (row["id"],),
        )
        connection.execute(
            "DELETE FROM pdf_pages WHERE document_id=?",
            (row["id"],),
        )
        connection.execute(
            "DELETE FROM page_text_fts WHERE reference_id=?",
            (row["reference_id"],),
        )

        for level, title, page_number in toc:
            connection.execute(
                """
                INSERT INTO pdf_bookmarks(document_id, level, title, page_number)
                VALUES (?, ?, ?, ?)
                """,
                (row["id"], int(level), str(title), int(page_number)),
            )

        text_page_count = 0
        image_only_page_count = 0
        total_text_characters = 0

        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            text = page.get_text("text") or ""
            text_chars = len(text.strip())
            image_count = len(page.get_images(full=True))
            has_text = int(text_chars >= text_threshold)

            if has_text:
                text_page_count += 1
            elif image_count > 0:
                image_only_page_count += 1

            total_text_characters += text_chars
            rect = page.rect

            connection.execute(
                """
                INSERT INTO pdf_pages(
                    document_id, page_number, text_content,
                    text_characters, has_text, image_count,
                    width_points, height_points, rotation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    page_index + 1,
                    text if store_text else None,
                    text_chars,
                    has_text,
                    image_count,
                    float(rect.width),
                    float(rect.height),
                    int(page.rotation),
                ),
            )

            if store_text and text.strip():
                connection.execute(
                    """
                    INSERT INTO page_text_fts(
                        reference_id, page_number, title,
                        section_path, text_content
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["reference_id"],
                        page_index + 1,
                        row["title"],
                        row["section_path"],
                        text,
                    ),
                )

        page_count = document.page_count
        searchable_text = int(text_page_count > 0)
        needs_ocr = int(page_count > 0 and text_page_count < max(1, page_count * 0.25))
        average_chars = total_text_characters / page_count if page_count else 0

        connection.execute(
            """
            UPDATE pdf_analysis
            SET analysis_status='complete',
                page_count=?,
                metadata_title=?,
                metadata_author=?,
                metadata_subject=?,
                metadata_keywords=?,
                metadata_creator=?,
                metadata_producer=?,
                creation_date=?,
                modification_date=?,
                bookmark_count=?,
                text_page_count=?,
                image_only_page_count=?,
                total_text_characters=?,
                average_text_characters=?,
                searchable_text=?,
                needs_ocr=?,
                encrypted=0,
                extraction_error=NULL,
                analyzed_at=CURRENT_TIMESTAMP
            WHERE document_id=?
            """,
            (
                page_count,
                metadata.get("title", ""),
                metadata.get("author", ""),
                metadata.get("subject", ""),
                metadata.get("keywords", ""),
                metadata.get("creator", ""),
                metadata.get("producer", ""),
                metadata.get("creationDate", ""),
                metadata.get("modDate", ""),
                len(toc),
                text_page_count,
                image_only_page_count,
                total_text_characters,
                average_chars,
                searchable_text,
                needs_ocr,
                row["id"],
            ),
        )

        document.close()
        connection.commit()

    except Exception as exc:
        connection.rollback()
        connection.execute(
            """
            UPDATE pdf_analysis
            SET analysis_status='error',
                extraction_error=?,
                analyzed_at=CURRENT_TIMESTAMP
            WHERE document_id=?
            """,
            (f"{type(exc).__name__}: {exc}", row["id"]),
        )
        connection.commit()
        raise


def analyze(
    connection: sqlite3.Connection,
    limit: int | None,
    retry_errors: bool,
    reference_id: str | None,
    store_text: bool,
    text_threshold: int,
) -> None:
    require_pymupdf()
    rows = selected_documents(connection, limit, retry_errors, reference_id)

    if not rows:
        print("No documents are waiting for analysis.")
        return

    run_id = connection.execute(
        "INSERT INTO analysis_runs(command) VALUES ('analyze')"
    ).lastrowid
    connection.commit()

    succeeded = 0
    failed = 0

    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row['reference_id']} | {row['title']}")
        try:
            extract_document(
                connection,
                row,
                store_text=store_text,
                text_threshold=text_threshold,
            )
            status = connection.execute(
                "SELECT analysis_status FROM pdf_analysis WHERE document_id=?",
                (row["id"],),
            ).fetchone()["analysis_status"]
            if status == "complete":
                succeeded += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            print(f"  ERROR: {exc}")

    connection.execute(
        """
        UPDATE analysis_runs
        SET completed_at=CURRENT_TIMESTAMP,
            processed=?, succeeded=?, failed=?
        WHERE id=?
        """,
        (len(rows), succeeded, failed, run_id),
    )
    connection.commit()

    print("\nAnalysis completed.")
    print(f"Processed: {len(rows)}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed:    {failed}")


def show_stats(connection: sqlite3.Connection) -> None:
    total = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    found = connection.execute(
        "SELECT COUNT(*) FROM documents WHERE file_exists=1"
    ).fetchone()[0]

    print(f"Documents: {total}")
    print(f"Files found: {found}")

    print("\nAnalysis status:")
    for row in connection.execute(
        """
        SELECT analysis_status, COUNT(*) count
        FROM pdf_analysis
        GROUP BY analysis_status
        ORDER BY count DESC
        """
    ):
        print(f"  {row['analysis_status']}: {row['count']}")

    totals = connection.execute(
        """
        SELECT
            COALESCE(SUM(page_count), 0) pages,
            COALESCE(SUM(bookmark_count), 0) bookmarks,
            COALESCE(SUM(total_text_characters), 0) characters,
            COALESCE(SUM(CASE WHEN needs_ocr=1 THEN 1 ELSE 0 END), 0) ocr_docs,
            COALESCE(SUM(CASE WHEN searchable_text=1 THEN 1 ELSE 0 END), 0) searchable_docs
        FROM pdf_analysis
        WHERE analysis_status='complete'
        """
    ).fetchone()

    print("\nExtracted intelligence:")
    print(f"  Pages: {totals['pages']}")
    print(f"  Bookmarks: {totals['bookmarks']}")
    print(f"  Text characters: {totals['characters']}")
    print(f"  Searchable documents: {totals['searchable_docs']}")
    print(f"  OCR candidates: {totals['ocr_docs']}")


def search_text(connection: sqlite3.Connection, query: str, limit: int) -> None:
    try:
        rows = connection.execute(
            """
            SELECT reference_id, page_number, title, section_path,
                   snippet(page_text_fts, 4, '[', ']', ' … ', 18) AS match_text
            FROM page_text_fts
            WHERE page_text_fts MATCH ?
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(
            f"Invalid FTS query: {query!r}. "
            "Try a simple word or a quoted phrase."
        ) from exc

    if not rows:
        print("No full-text matches.")
        return

    for row in rows:
        print(f"{row['reference_id']} | page {row['page_number']} | {row['title']}")
        if row["section_path"]:
            print(f"  Section: {row['section_path']}")
        print(f"  {row['match_text']}")


def show_document(connection: sqlite3.Connection, reference_id: str) -> None:
    row = connection.execute(
        """
        SELECT d.*, a.*
        FROM documents d
        JOIN pdf_analysis a ON a.document_id=d.id
        WHERE d.reference_id=?
        """,
        (reference_id,),
    ).fetchone()

    if not row:
        print("Document not found.")
        return

    fields = [
        ("Reference", row["reference_id"]),
        ("Title", row["title"]),
        ("Manual", row["manual_type_normalized"]),
        ("System", row["system_name"]),
        ("Engine", row["engine_code"]),
        ("Transmission", row["transmission_code"]),
        ("Status", row["analysis_status"]),
        ("Pages", row["page_count"]),
        ("Bookmarks", row["bookmark_count"]),
        ("Text pages", row["text_page_count"]),
        ("Image-only pages", row["image_only_page_count"]),
        ("Characters", row["total_text_characters"]),
        ("Searchable", row["searchable_text"]),
        ("Needs OCR", row["needs_ocr"]),
        ("Path", row["resolved_local_path"]),
        ("Error", row["extraction_error"]),
    ]

    for label, value in fields:
        print(f"{label:18}: {'' if value is None else value}")


def export_ocr_queue(connection: sqlite3.Connection, output_path: Path) -> int:
    rows = connection.execute(
        """
        SELECT d.reference_id, d.title, d.manual_type_normalized,
               d.system_name, a.page_count, a.text_page_count,
               a.image_only_page_count, d.resolved_local_path
        FROM documents d
        JOIN pdf_analysis a ON a.document_id=d.id
        WHERE a.analysis_status='complete' AND a.needs_ocr=1
        ORDER BY d.manual_type_normalized, d.system_name, d.title
        """
    ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "reference_id", "title", "manual_type_normalized", "system_name",
        "page_count", "text_page_count", "image_only_page_count",
        "resolved_local_path",
    ]

    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(tuple(row))

    return len(rows)


def export_analysis(connection: sqlite3.Connection, output_path: Path) -> int:
    rows = connection.execute(
        """
        SELECT d.reference_id, d.title, d.manual_type_normalized,
               d.system_name, d.engine_code, d.transmission_code,
               a.analysis_status, a.page_count, a.bookmark_count,
               a.text_page_count, a.image_only_page_count,
               a.total_text_characters, a.average_text_characters,
               a.searchable_text, a.needs_ocr, a.encrypted,
               a.extraction_error, a.analyzed_at
        FROM documents d
        JOIN pdf_analysis a ON a.document_id=d.id
        ORDER BY d.reference_id
        """
    ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(rows[0].keys() if rows else [])
        for row in rows:
            writer.writerow(tuple(row))

    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Toyota Engineering Archive PDF Intelligence Engine v0.3"
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("toyota_archive_v0.3.db"),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).with_name("schema_v0.3.sql"),
    )

    commands = parser.add_subparsers(dest="command", required=True)

    p_import = commands.add_parser("import")
    p_import.add_argument("--catalog", type=Path, required=True)
    p_import.add_argument(
        "--archive-root",
        type=Path,
        help="Folder containing the PDFs directory",
    )

    p_analyze = commands.add_parser("analyze")
    p_analyze.add_argument("--limit", type=int)
    p_analyze.add_argument("--retry-errors", action="store_true")
    p_analyze.add_argument("--reference-id")
    p_analyze.add_argument(
        "--no-store-text",
        action="store_true",
        help="Inspect PDFs without storing page text or building FTS",
    )
    p_analyze.add_argument(
        "--text-threshold",
        type=int,
        default=20,
        help="Minimum trimmed characters for a page to count as text-bearing",
    )

    commands.add_parser("stats")

    p_search = commands.add_parser("search-text")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=30)

    p_show = commands.add_parser("show")
    p_show.add_argument("reference_id")

    p_ocr = commands.add_parser("export-ocr-queue")
    p_ocr.add_argument(
        "--output",
        type=Path,
        default=Path("ocr_queue.csv"),
    )

    p_export = commands.add_parser("export-analysis")
    p_export.add_argument(
        "--output",
        type=Path,
        default=Path("pdf_analysis.csv"),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    connection = connect(args.database)
    initialise_database(connection, args.schema)

    try:
        if args.command == "import":
            inserted, updated = import_catalog(
                connection,
                args.catalog,
                args.archive_root.resolve() if args.archive_root else None,
            )
            print(f"Inserted: {inserted}")
            print(f"Updated:  {updated}")
            show_stats(connection)

        elif args.command == "analyze":
            analyze(
                connection,
                limit=args.limit,
                retry_errors=args.retry_errors,
                reference_id=args.reference_id,
                store_text=not args.no_store_text,
                text_threshold=args.text_threshold,
            )

        elif args.command == "stats":
            show_stats(connection)

        elif args.command == "search-text":
            search_text(connection, args.query, args.limit)

        elif args.command == "show":
            show_document(connection, args.reference_id)

        elif args.command == "export-ocr-queue":
            count = export_ocr_queue(connection, args.output)
            print(f"Exported {count} OCR candidates to {args.output}")

        elif args.command == "export-analysis":
            count = export_analysis(connection, args.output)
            print(f"Exported {count} rows to {args.output}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
