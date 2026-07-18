from pathlib import Path
from datetime import datetime, timezone
import argparse, csv, sqlite3, sys

from database.db import connect, apply_schema, ensure_v041_component_schema
from database.catalog_adapter import discover_text_source, iter_source_documents
from knowledge.normalize import normalize_term
from extractors.component_extractor import compile_patterns, extract_components
from extractors.procedure_extractor import extract_procedure_blocks
from search.component_search import search_components, component_details
from search.procedure_search import procedure_details, procedure_type_counts

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

BASE = Path(__file__).resolve().parent
SCHEMA = BASE/"database/schema_v0.4.2.sql"
COMPONENTS = BASE/"data/components.csv"
ALIASES = BASE/"data/aliases.csv"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_component_patterns(conn):
    rows = conn.execute(
        '''SELECT a.component_id,c.canonical_name,a.alias
           FROM component_aliases a JOIN components c USING(component_id)'''
    ).fetchall()
    if not rows:
        raise SystemExit("Run init first.")
    return compile_patterns((r[0],r[1],r[2]) for r in rows)

def cmd_init(a):
    conn = connect(a.db)
    ensure_v041_component_schema(conn)
    apply_schema(conn, SCHEMA)
    with COMPONENTS.open(encoding="utf-8-sig", newline="") as f:
        components = list(csv.DictReader(f))
    with conn:
        for r in components:
            name = r["canonical_name"].strip()
            conn.execute(
                '''INSERT INTO components(canonical_name,normalized_name,system_name,description)
                   VALUES(?,?,?,?)
                   ON CONFLICT(normalized_name) DO UPDATE SET
                   canonical_name=excluded.canonical_name,
                   system_name=excluded.system_name,
                   description=excluded.description,
                   updated_at=CURRENT_TIMESTAMP''',
                (name, normalize_term(name), r["system_name"].strip(), r["description"].strip()))
        ids = {normalize_term(r["canonical_name"]): r["component_id"]
               for r in conn.execute("SELECT component_id,canonical_name FROM components")}
        for r in components:
            name = r["canonical_name"].strip()
            conn.execute(
                '''INSERT INTO component_aliases(component_id,alias,normalized_alias)
                   VALUES(?,?,?) ON CONFLICT(normalized_alias) DO UPDATE SET
                   component_id=excluded.component_id, alias=excluded.alias''',
                (ids[normalize_term(name)], name, normalize_term(name)))
        with ALIASES.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                cid = ids.get(normalize_term(r["canonical_name"]))
                if cid:
                    alias = r["alias"].strip()
                    conn.execute(
                        '''INSERT INTO component_aliases(component_id,alias,normalized_alias)
                           VALUES(?,?,?) ON CONFLICT(normalized_alias) DO UPDATE SET
                           component_id=excluded.component_id, alias=excluded.alias''',
                        (cid, alias, normalize_term(alias)))
    print(f"Initialized {a.db}")
    print("Components:", conn.execute("SELECT COUNT(*) FROM components").fetchone()[0])
    print("Aliases:   ", conn.execute("SELECT COUNT(*) FROM component_aliases").fetchone()[0])

def cmd_detect(a):
    conn = connect(a.db)
    table, mapping = discover_text_source(conn)
    print("Text source table:", table)
    for k, v in mapping.items():
        print(f"  {k:10}: {v}")

def cmd_extract(a):
    conn = connect(a.db)
    ensure_v041_component_schema(conn)
    apply_schema(conn, SCHEMA)
    patterns = load_component_patterns(conn)
    run_id = conn.execute(
        "INSERT INTO component_extraction_runs(started_at,status) VALUES(?,'running')",(now(),)
    ).lastrowid
    conn.commit()
    deleted = 0
    if a.rebuild:
        deleted = conn.execute("DELETE FROM document_components").rowcount
        conn.commit()
    seen=processed=inserted=existing=updated=errors=0
    try:
        for src in iter_source_documents(conn):
            seen += 1
            if a.limit and processed >= a.limit:
                break
            try:
                mentions = extract_components(src.text, patterns)
                with conn:
                    for m in mentions:
                        current = conn.execute(
                            '''SELECT reference_id, occurrence_count, first_context
                               FROM document_components
                               WHERE document_id=? AND component_id=? AND page_number IS ?''',
                            (src.document_id, m.component_id, src.page_number)
                        ).fetchone()
                        if current is None:
                            conn.execute(
                                '''INSERT INTO document_components(
                                   document_id,reference_id,component_id,page_number,
                                   occurrence_count,first_context,extracted_at)
                                   VALUES(?,?,?,?,?,?,?)''',
                                (src.document_id,src.reference_id,m.component_id,src.page_number,
                                 m.count,m.first_context,now()))
                            inserted += 1
                            continue

                        existing += 1
                        changed = (
                            current["reference_id"] != src.reference_id or
                            current["occurrence_count"] != m.count or
                            current["first_context"] != m.first_context
                        )
                        if changed:
                            conn.execute(
                                '''UPDATE document_components
                                   SET reference_id=?,
                                       occurrence_count=?,
                                       first_context=?,
                                       extracted_at=?
                                   WHERE document_id=? AND component_id=? AND page_number IS ?''',
                                (src.reference_id,m.count,m.first_context,now(),
                                 src.document_id,m.component_id,src.page_number))
                            updated += 1
                processed += 1
                if a.progress and processed % a.progress == 0:
                    print(f"Scanned {processed:,} pages; inserted {inserted:,}; existing {existing:,}")
            except Exception as e:
                errors += 1
                print(f"Error {src.document_key}: {e}", file=sys.stderr)
        status = "completed" if errors == 0 else "completed_with_errors"
        with conn:
            conn.execute(
                '''UPDATE component_extraction_runs SET finished_at=?,status=?,
                   documents_seen=?,documents_processed=?,mentions_written=?,error_count=?
                   WHERE run_id=?''',
                (now(),status,seen,processed,inserted,errors,run_id))
    except Exception as e:
        with conn:
            conn.execute("UPDATE component_extraction_runs SET finished_at=?,status='failed',notes=? WHERE run_id=?",
                         (now(),str(e),run_id))
        raise
    print("Extraction completed.")
    print(f"Pages scanned:      {processed:,}")
    if a.rebuild:
        print(f"Rows deleted:       {deleted:,}")
    print(f"New rows inserted:  {inserted:,}")
    print(f"Existing rows:      {existing:,}")
    print(f"Rows updated:       {updated:,}")
    print(f"Errors:             {errors:,}")

def iter_procedure_pages(conn):
    return conn.execute(
        '''
        SELECT p.document_id,
               p.page_number,
               p.text_content,
               d.reference_id,
               d.title,
               d.section_path
        FROM pdf_pages p
        JOIN documents d ON d.id = p.document_id
        WHERE p.text_content IS NOT NULL
        ORDER BY p.document_id, p.page_number
        '''
    )

def cmd_extract_procedures(a):
    conn = connect(a.db)
    ensure_v041_component_schema(conn)
    apply_schema(conn, SCHEMA)
    patterns = load_component_patterns(conn)
    deleted = 0
    if a.rebuild:
        deleted = conn.execute("DELETE FROM procedures").rowcount
        conn.commit()

    scanned=blocks_seen=inserted=existing=updated=errors=0
    try:
        for page in iter_procedure_pages(conn):
            if a.limit and scanned >= a.limit:
                break
            scanned += 1
            try:
                blocks = extract_procedure_blocks(
                    page["text_content"],
                    document_title=page["title"],
                    section_path=page["section_path"],
                )
                if not blocks:
                    continue
                with conn:
                    for block in blocks:
                        blocks_seen += 1
                        association_text = f"{block.title} {block.context}"
                        mentions = extract_components(association_text, patterns)
                        for mention in mentions:
                            current = conn.execute(
                                '''SELECT context, step_count
                                   FROM procedures
                                   WHERE component_id=? AND document_id=? AND page_number=?
                                     AND procedure_type=? AND title IS ?''',
                                (mention.component_id,page["document_id"],page["page_number"],
                                 block.procedure_type,block.title)
                            ).fetchone()
                            if current is None:
                                conn.execute(
                                    '''INSERT INTO procedures(
                                       component_id,document_id,page_number,procedure_type,
                                       title,context,step_count,extracted_at)
                                       VALUES(?,?,?,?,?,?,?,?)''',
                                    (mention.component_id,page["document_id"],page["page_number"],
                                     block.procedure_type,block.title,block.context,
                                     block.step_count,now()))
                                inserted += 1
                                continue

                            existing += 1
                            if current["context"] != block.context or current["step_count"] != block.step_count:
                                conn.execute(
                                    '''UPDATE procedures
                                       SET context=?, step_count=?, extracted_at=?
                                       WHERE component_id=? AND document_id=? AND page_number=?
                                         AND procedure_type=? AND title IS ?''',
                                    (block.context,block.step_count,now(),mention.component_id,
                                     page["document_id"],page["page_number"],block.procedure_type,
                                     block.title))
                                updated += 1
                if a.progress and scanned % a.progress == 0:
                    print(f"Scanned {scanned:,} pages; procedures inserted {inserted:,}; existing {existing:,}")
            except Exception as e:
                errors += 1
                print(f"Error {page['reference_id']} page {page['page_number']}: {e}", file=sys.stderr)
    finally:
        pass

    print("Procedure extraction completed.")
    print(f"Pages scanned:       {scanned:,}")
    if a.rebuild:
        print(f"Rows deleted:        {deleted:,}")
    print(f"Procedure blocks:    {blocks_seen:,}")
    print(f"New rows inserted:   {inserted:,}")
    print(f"Existing rows:       {existing:,}")
    print(f"Rows updated:        {updated:,}")
    print(f"Errors:              {errors:,}")

def cmd_component(a):
    conn = connect(a.db)
    rows = search_components(conn, a.query, a.limit)
    if not rows:
        print("No matching component.")
        return
    for r in rows:
        print(f"{r['component_id']:4} | {r['canonical_name']} | {r['system_name']} | "
              f"{r['document_count']} documents | {r['occurrence_count']} occurrences")
    if a.details or (len(rows)==1 and not a.procedures):
        c, docs = component_details(conn, rows[0]["component_id"], a.doc_limit)
        print(f"\n{c['canonical_name']} - {c['system_name']}")
        for d in docs:
            ref = d["reference_id"] or str(d["document_id"])
            category = d["manual_type_normalized"] or d["system_name"] or ""
            print(f"  Component: {c['canonical_name']}")
            print(f"  Document:  {d['title']}")
            print(f"  Reference: {ref}")
            print(f"  Category:  {category}")
            if d["section_path"]:
                print(f"  Section:   {d['section_path']}")
            print(f"  Page:      {d['page_number']}")
            print(f"  Mentions:  {d['occurrence_count']}")
            if a.context and d["first_context"]:
                print("  Context:")
                print("   ", d["first_context"])
            print()
    if a.procedures:
        for r in rows:
            counts = procedure_type_counts(conn, r["component_id"])
            if not counts:
                continue
            print(f"\n{r['canonical_name']} procedures")
            for item in counts:
                print(f"  {item['procedure_type']}: {item['procedure_count']}")

def cmd_procedure(a):
    conn = connect(a.db)
    rows = search_components(conn, a.query, a.limit)
    if not rows:
        print("No matching component.")
        return
    for component in rows:
        procedures = procedure_details(conn, component["component_id"], a.type, a.doc_limit)
        if not procedures:
            continue
        print(f"\n{component['canonical_name']}")
        last_type = None
        for proc in procedures:
            if proc["procedure_type"] != last_type:
                last_type = proc["procedure_type"]
                print(f"\n{last_type}")
                print("-" * len(last_type))
            category = proc["manual_type_normalized"] or proc["system_name"] or ""
            print(f"{proc['document_title']} | {category} | {proc['reference_id']} | page {proc['page_number']}")
            if proc["step_count"]:
                print(f"Steps detected: {proc['step_count']}")
            if a.context:
                print(proc["context"])
            print()

def cmd_stats(a):
    conn = connect(a.db)
    for label, sql in [
        ("Components","SELECT COUNT(*) FROM components"),
        ("Aliases","SELECT COUNT(*) FROM component_aliases"),
        ("Document-component rows","SELECT COUNT(*) FROM document_components"),
        ("Documents represented","SELECT COUNT(DISTINCT document_id) FROM document_components"),
        ("Total occurrences","SELECT COALESCE(SUM(occurrence_count),0) FROM document_components"),
        ("Procedures","SELECT COUNT(*) FROM procedures"),
        ("Procedure components","SELECT COUNT(DISTINCT component_id) FROM procedures")]:
        print(f"{label:24} {conn.execute(sql).fetchone()[0]:,}")

def main():
    p=argparse.ArgumentParser(description="Toyota Engineering Archive v0.4.2")
    p.add_argument("--db", type=Path, default=BASE/"toyota_archive_v0.4.db")
    s=p.add_subparsers(dest="cmd", required=True)
    x=s.add_parser("init"); x.set_defaults(func=cmd_init)
    x=s.add_parser("detect-source"); x.set_defaults(func=cmd_detect)
    x=s.add_parser("extract-components")
    x.add_argument("--limit",type=int); x.add_argument("--rebuild",action="store_true")
    x.add_argument("--progress",type=int,default=100); x.set_defaults(func=cmd_extract)
    x=s.add_parser("extract-procedures")
    x.add_argument("--limit",type=int); x.add_argument("--rebuild",action="store_true")
    x.add_argument("--progress",type=int,default=100); x.set_defaults(func=cmd_extract_procedures)
    x=s.add_parser("component"); x.add_argument("query"); x.add_argument("--limit",type=int,default=20)
    x.add_argument("--doc-limit",type=int,default=100); x.add_argument("--details",action="store_true")
    x.add_argument("--context",action="store_true"); x.add_argument("--procedures",action="store_true")
    x.set_defaults(func=cmd_component)
    x=s.add_parser("procedure"); x.add_argument("query"); x.add_argument("--limit",type=int,default=20)
    x.add_argument("--doc-limit",type=int,default=50); x.add_argument("--type")
    x.add_argument("--context",action="store_true"); x.set_defaults(func=cmd_procedure)
    x=s.add_parser("stats"); x.set_defaults(func=cmd_stats)
    a=p.parse_args()
    try: a.func(a)
    except (sqlite3.Error,RuntimeError) as e: raise SystemExit(str(e))

if __name__=="__main__":
    main()
