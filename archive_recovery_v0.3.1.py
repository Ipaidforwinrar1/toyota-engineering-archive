
#!/usr/bin/env python3
"""
Toyota Engineering Archive — Recovery & Maintenance v0.3.1

Companion utility for Toyota Archive Catalog v0.3.

Commands:
  report-missing
  retry-missing
  sync-files
  stats
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DB = "toyota_archive_v0.3.db"
USER_AGENT = "Toyota-Engineering-Archive/0.3.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def pick_column(cols: set[str], *names: str) -> str | None:
    return next((n for n in names if n in cols), None)


def document_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    cols = columns(con, "documents")
    required = {"id", "reference_id", "title"}
    missing = required - cols
    if missing:
        raise RuntimeError(f"Unsupported database: documents table lacks {sorted(missing)}")
    return list(con.execute("SELECT * FROM documents ORDER BY reference_id"))


def resolve_path(row: sqlite3.Row, archive_root: Path | None) -> Path | None:
    keys = set(row.keys())
    raw = None
    for name in ("resolved_local_path", "original_local_path", "local_path"):
        if name in keys and row[name]:
            raw = str(row[name])
            break
    if not raw:
        return None

    p = Path(raw)
    if p.is_absolute():
        return p
    if archive_root is not None:
        return archive_root / p
    return p


def is_valid_pdf(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 5:
            return False
        with path.open("rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def missing_rows(
    con: sqlite3.Connection,
    archive_root: Path | None,
) -> list[tuple[sqlite3.Row, Path | None, str]]:
    output = []
    for row in document_rows(con):
        path = resolve_path(row, archive_root)
        if path is None:
            output.append((row, None, "no local path"))
        elif not path.exists():
            output.append((row, path, "file missing"))
        elif not is_valid_pdf(path):
            output.append((row, path, "invalid PDF"))
    return output


def ensure_recovery_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS recovery_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            reference_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            source_url TEXT,
            target_path TEXT,
            outcome TEXT NOT NULL,
            http_status INTEGER,
            error_type TEXT,
            error_message TEXT,
            bytes_downloaded INTEGER,
            sha256 TEXT,
            elapsed_seconds REAL,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        );

        CREATE INDEX IF NOT EXISTS idx_recovery_attempts_reference
            ON recovery_attempts(reference_id);
        CREATE INDEX IF NOT EXISTS idx_recovery_attempts_outcome
            ON recovery_attempts(outcome);
        """
    )
    con.commit()


def update_document_success(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    final_path: Path,
    digest: str,
) -> None:
    cols = columns(con, "documents")
    updates: dict[str, Any] = {}

    mapping = {
        "resolved_local_path": str(final_path),
        "file_exists": 1,
        "pdf_valid": 1,
        "sha256": digest,
        "download_status": "downloaded",
        "error": None,
        "verified_at": utc_now(),
    }
    for key, value in mapping.items():
        if key in cols:
            updates[key] = value

    if updates:
        clause = ", ".join(f"{k}=?" for k in updates)
        con.execute(
            f"UPDATE documents SET {clause} WHERE id=?",
            [*updates.values(), row["id"]],
        )

    if table_exists(con, "pdf_analysis"):
        pa_cols = columns(con, "pdf_analysis")
        if "document_id" in pa_cols:
            existing = con.execute(
                "SELECT 1 FROM pdf_analysis WHERE document_id=?",
                (row["id"],),
            ).fetchone()
            if existing:
                reset = {}
                for key, value in {
                    "analysis_status": "pending",
                    "extraction_error": None,
                    "analyzed_at": None,
                }.items():
                    if key in pa_cols:
                        reset[key] = value
                if reset:
                    clause = ", ".join(f"{k}=?" for k in reset)
                    con.execute(
                        f"UPDATE pdf_analysis SET {clause} WHERE document_id=?",
                        [*reset.values(), row["id"]],
                    )
            else:
                fields = ["document_id"]
                vals: list[Any] = [row["id"]]
                if "analysis_status" in pa_cols:
                    fields.append("analysis_status")
                    vals.append("pending")
                q = ",".join("?" for _ in fields)
                con.execute(
                    f"INSERT INTO pdf_analysis ({','.join(fields)}) VALUES ({q})",
                    vals,
                )


def update_document_failure(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    message: str,
) -> None:
    cols = columns(con, "documents")
    updates = {}
    if "file_exists" in cols:
        updates["file_exists"] = 0
    if "download_status" in cols:
        updates["download_status"] = "failed"
    if "error" in cols:
        updates["error"] = message[:2000]
    if updates:
        clause = ", ".join(f"{k}=?" for k in updates)
        con.execute(
            f"UPDATE documents SET {clause} WHERE id=?",
            [*updates.values(), row["id"]],
        )


def log_attempt(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    source_url: str | None,
    target_path: Path | None,
    outcome: str,
    http_status: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    bytes_downloaded: int | None = None,
    digest: str | None = None,
    elapsed_seconds: float | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO recovery_attempts (
            document_id, reference_id, attempted_at, source_url, target_path,
            outcome, http_status, error_type, error_message,
            bytes_downloaded, sha256, elapsed_seconds
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"], row["reference_id"], utc_now(), source_url,
            str(target_path) if target_path else None, outcome, http_status,
            error_type, error_message, bytes_downloaded, digest, elapsed_seconds,
        ),
    )


def safe_target(
    row: sqlite3.Row,
    archive_root: Path | None,
    recovery_dir: Path,
) -> Path:
    expected = resolve_path(row, archive_root)
    if expected is not None:
        # Leave margin below the classic Windows MAX_PATH threshold.
        if len(str(expected)) < 235:
            return expected
    return recovery_dir / f"{row['reference_id']}.pdf"


def download_one(
    url: str,
    target: Path,
    timeout: float,
) -> tuple[int, str]:
    target.parent.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"},
    )

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.stem + ".",
        suffix=".part",
        dir=str(target.parent),
    )
    os.close(fd)
    tmp = Path(tmp_name)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            with tmp.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)

        if not is_valid_pdf(tmp):
            raise ValueError("Downloaded file does not have a valid PDF header")

        digest = sha256_file(tmp)
        size = tmp.stat().st_size
        os.replace(tmp, target)
        return size, digest
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def cmd_report(args: argparse.Namespace) -> int:
    db = Path(args.db)
    root = Path(args.archive_root) if args.archive_root else None
    with connect(db) as con:
        rows = missing_rows(con, root)

        print(f"Missing or invalid documents: {len(rows)}")
        print()

        type_counts = Counter()
        reason_counts = Counter()

        for row, path, reason in rows:
            keys = set(row.keys())
            manual_type = (
                row["manual_type_normalized"]
                if "manual_type_normalized" in keys
                else row["manual_type"] if "manual_type" in keys else "Unknown"
            )
            type_counts[manual_type or "Unknown"] += 1
            reason_counts[reason] += 1

            if not args.summary_only:
                print(f"{row['reference_id']} | {row['title']}")
                print(f"  Type: {manual_type}")
                print(f"  Reason: {reason}")
                print(f"  Expected: {path or '(none)'}")
                if "source_url" in keys:
                    print(f"  URL: {row['source_url'] or '(none)'}")
                if "error" in keys and row["error"]:
                    print(f"  Previous error: {row['error']}")
                print()

        print("By reason:")
        for name, count in reason_counts.most_common():
            print(f"  {name}: {count}")

        print("\nBy manual type:")
        for name, count in type_counts.most_common():
            print(f"  {name}: {count}")

        if args.csv:
            out = Path(args.csv)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow([
                    "reference_id", "title", "manual_type", "reason",
                    "expected_path", "source_url", "previous_error",
                ])
                for row, path, reason in rows:
                    keys = set(row.keys())
                    mt = (
                        row["manual_type_normalized"]
                        if "manual_type_normalized" in keys
                        else row["manual_type"] if "manual_type" in keys else ""
                    )
                    writer.writerow([
                        row["reference_id"], row["title"], mt, reason,
                        str(path) if path else "",
                        row["source_url"] if "source_url" in keys else "",
                        row["error"] if "error" in keys else "",
                    ])
            print(f"\nCSV written: {out}")

    return 0


def cmd_retry(args: argparse.Namespace) -> int:
    db = Path(args.db)
    root = Path(args.archive_root) if args.archive_root else None
    recovery_dir = Path(args.recovery_dir)
    if not recovery_dir.is_absolute():
        recovery_dir = db.parent / recovery_dir

    with connect(db) as con:
        ensure_recovery_tables(con)
        rows = missing_rows(con, root)
        if args.limit is not None:
            rows = rows[: args.limit]

        print(f"Documents selected: {len(rows)}")
        print(f"Fallback recovery directory: {recovery_dir}")
        print()

        succeeded = failed = skipped = 0

        for index, (row, _, _) in enumerate(rows, 1):
            keys = set(row.keys())
            url = row["source_url"] if "source_url" in keys else None
            target = safe_target(row, root, recovery_dir)
            print(f"[{index}/{len(rows)}] {row['reference_id']} | {row['title']}")

            if not url:
                message = "No source URL stored in database"
                print(f"  SKIP: {message}")
                log_attempt(
                    con, row, source_url=None, target_path=target,
                    outcome="skipped", error_type="missing_url",
                    error_message=message,
                )
                update_document_failure(con, row, message)
                con.commit()
                skipped += 1
                continue

            last_error = None
            for attempt in range(1, args.attempts + 1):
                started = time.perf_counter()
                try:
                    size, digest = download_one(url, target, args.timeout)
                    elapsed = time.perf_counter() - started
                    update_document_success(con, row, target, digest)
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="success", bytes_downloaded=size,
                        digest=digest, elapsed_seconds=elapsed,
                    )
                    con.commit()
                    print(f"  OK: {size:,} bytes -> {target}")
                    succeeded += 1
                    last_error = None
                    break
                except urllib.error.HTTPError as exc:
                    elapsed = time.perf_counter() - started
                    last_error = f"HTTP {exc.code}: {exc.reason}"
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="failed", http_status=exc.code,
                        error_type="http_error", error_message=last_error,
                        elapsed_seconds=elapsed,
                    )
                    if exc.code in (404, 410):
                        break
                except urllib.error.URLError as exc:
                    elapsed = time.perf_counter() - started
                    last_error = f"Network error: {exc.reason}"
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="failed", error_type="network_error",
                        error_message=last_error, elapsed_seconds=elapsed,
                    )
                except TimeoutError as exc:
                    elapsed = time.perf_counter() - started
                    last_error = f"Timeout: {exc}"
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="failed", error_type="timeout",
                        error_message=last_error, elapsed_seconds=elapsed,
                    )
                except OSError as exc:
                    elapsed = time.perf_counter() - started
                    last_error = f"Filesystem error: {exc}"
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="failed", error_type="filesystem_error",
                        error_message=last_error, elapsed_seconds=elapsed,
                    )
                except Exception as exc:
                    elapsed = time.perf_counter() - started
                    last_error = f"{type(exc).__name__}: {exc}"
                    log_attempt(
                        con, row, source_url=url, target_path=target,
                        outcome="failed",
                        error_type=type(exc).__name__.lower(),
                        error_message=last_error,
                        elapsed_seconds=elapsed,
                    )

                con.commit()
                print(f"  Attempt {attempt}/{args.attempts} failed: {last_error}")
                if attempt < args.attempts:
                    time.sleep(args.delay * attempt)

            if last_error is not None:
                update_document_failure(con, row, last_error)
                con.commit()
                failed += 1

        print("\nRecovery completed.")
        print(f"Succeeded: {succeeded}")
        print(f"Failed:    {failed}")
        print(f"Skipped:   {skipped}")
        print("\nRecovered files are marked pending for PDF analysis.")
        print("Run the v0.3 analyzer again to index them:")
        print("  py .\\pdf_intelligence_v0.3.py analyze")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    db = Path(args.db)
    root = Path(args.archive_root) if args.archive_root else None
    with connect(db) as con:
        cols = columns(con, "documents")
        changed = 0
        valid = invalid = missing = 0

        for row in document_rows(con):
            path = resolve_path(row, root)
            exists = bool(path and path.exists())
            pdf_ok = bool(path and is_valid_pdf(path))
            if not exists:
                missing += 1
            elif pdf_ok:
                valid += 1
            else:
                invalid += 1

            updates = {}
            if "file_exists" in cols:
                updates["file_exists"] = int(exists)
            if "pdf_valid" in cols:
                updates["pdf_valid"] = int(pdf_ok)
            if "download_status" in cols:
                updates["download_status"] = "downloaded" if pdf_ok else "failed"

            if updates:
                clause = ", ".join(f"{k}=?" for k in updates)
                con.execute(
                    f"UPDATE documents SET {clause} WHERE id=?",
                    [*updates.values(), row["id"]],
                )
                changed += 1

        con.commit()
        print(f"Documents checked: {changed}")
        print(f"Valid PDFs:        {valid}")
        print(f"Missing files:     {missing}")
        print(f"Invalid PDFs:      {invalid}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db = Path(args.db)
    with connect(db) as con:
        ensure_recovery_tables(con)
        total = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        attempts = con.execute("SELECT COUNT(*) FROM recovery_attempts").fetchone()[0]
        success = con.execute(
            "SELECT COUNT(*) FROM recovery_attempts WHERE outcome='success'"
        ).fetchone()[0]
        latest = con.execute(
            """
            SELECT reference_id, outcome, error_type, attempted_at
            FROM recovery_attempts
            ORDER BY id DESC LIMIT 10
            """
        ).fetchall()

        print(f"Documents: {total}")
        print(f"Recovery attempts: {attempts}")
        print(f"Successful recoveries: {success}")
        if latest:
            print("\nLatest attempts:")
            for row in latest:
                detail = f" ({row['error_type']})" if row["error_type"] else ""
                print(
                    f"  {row['attempted_at']} | {row['reference_id']} | "
                    f"{row['outcome']}{detail}"
                )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Toyota Archive recovery and maintenance utility v0.3.1"
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report-missing", help="List missing or invalid PDFs")
    report.add_argument("--archive-root")
    report.add_argument("--csv", help="Write detailed report to CSV")
    report.add_argument("--summary-only", action="store_true")
    report.set_defaults(func=cmd_report)

    retry = sub.add_parser("retry-missing", help="Retry only missing or invalid PDFs")
    retry.add_argument("--archive-root")
    retry.add_argument(
        "--recovery-dir", default="_recovered",
        help="Fallback directory for long paths (default: _recovered beside DB)",
    )
    retry.add_argument("--attempts", type=int, default=3)
    retry.add_argument("--timeout", type=float, default=60.0)
    retry.add_argument("--delay", type=float, default=2.0)
    retry.add_argument("--limit", type=int)
    retry.set_defaults(func=cmd_retry)

    sync = sub.add_parser("sync-files", help="Synchronize DB file flags with disk")
    sync.add_argument("--archive-root")
    sync.set_defaults(func=cmd_sync)

    stats = sub.add_parser("stats", help="Show recovery history")
    stats.set_defaults(func=cmd_stats)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted. Completed attempts were already committed.")
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
