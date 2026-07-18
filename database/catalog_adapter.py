from dataclasses import dataclass
from .db import table_exists, column_names

@dataclass(frozen=True)
class SourceDocument:
    document_id: int | None
    document_key: str
    reference_id: str | None
    title: str
    section_path: str
    text: str
    page_number: int | None

TABLES = ("pdf_pages", "document_pages", "page_text", "pdf_analysis", "documents")

def first(cols, choices):
    return next((x for x in choices if x in cols), None)

def discover_text_source(conn):
    if table_exists(conn, "pdf_pages") and table_exists(conn, "documents"):
        page_cols = column_names(conn, "pdf_pages")
        doc_cols = column_names(conn, "documents")
        if {"document_id", "page_number", "text_content"}.issubset(page_cols) and "id" in doc_cols:
            return "pdf_pages JOIN documents", {
                "document_id": "pdf_pages.document_id",
                "key": "documents.reference_id" if "reference_id" in doc_cols else "pdf_pages.document_id",
                "reference": "documents.reference_id" if "reference_id" in doc_cols else None,
                "title": "documents.title" if "title" in doc_cols else None,
                "section": "documents.section_path" if "section_path" in doc_cols else None,
                "page": "pdf_pages.page_number",
                "text": "pdf_pages.text_content",
            }
    for table in TABLES:
        if not table_exists(conn, table):
            continue
        cols = column_names(conn, table)
        text = first(cols, ("extracted_text","page_text","text_content","content","full_text","text"))
        key = first(cols, ("document_id","reference_id","id","pdf_id"))
        if text and key:
            return table, {
                "key": key,
                "reference": first(cols, ("reference_id",)),
                "title": first(cols, ("title","document_title","filename")),
                "section": first(cols, ("section_path",)),
                "page": first(cols, ("page_number","page","page_index")),
                "text": text,
            }
    raise RuntimeError("No usable extracted-text table was found in the database.")

def iter_source_documents(conn):
    table, m = discover_text_source(conn)
    if table == "pdf_pages JOIN documents":
        sql = """
            SELECT p.document_id AS document_id,
                   d.reference_id AS document_key,
                   d.reference_id AS reference_id,
                   d.title AS title,
                   d.section_path AS section_path,
                   p.text_content AS body_text,
                   p.page_number AS page_number
            FROM pdf_pages p
            JOIN documents d ON d.id = p.document_id
            WHERE p.text_content IS NOT NULL
        """
        for r in conn.execute(sql):
            yield SourceDocument(r["document_id"], str(r["document_key"]), r["reference_id"],
                                 r["title"] or "", r["section_path"] or "",
                                 r["body_text"] or "", r["page_number"])
        return

    cols = [
        "NULL AS document_id",
        f'"{m["key"]}" AS document_key',
        f'"{m["text"]}" AS body_text',
        f'"{m["reference"]}" AS reference_id' if m["reference"] else "NULL AS reference_id",
        f'"{m["title"]}" AS title' if m["title"] else "'' AS title",
        f'"{m["section"]}" AS section_path' if m["section"] else "'' AS section_path",
        f'"{m["page"]}" AS page_number' if m["page"] else "NULL AS page_number",
    ]
    sql = f'SELECT {", ".join(cols)} FROM "{table}" WHERE "{m["text"]}" IS NOT NULL'
    for r in conn.execute(sql):
        yield SourceDocument(r["document_id"], str(r["document_key"]), r["reference_id"], r["title"] or "",
                             r["section_path"] or "", r["body_text"] or "", r["page_number"])
