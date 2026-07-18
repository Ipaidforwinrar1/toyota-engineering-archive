from pathlib import Path
import sqlite3

def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def apply_schema(conn, schema_path: Path):
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()

def ensure_v041_component_schema(conn):
    if not table_exists(conn, "document_components"):
        return
    cols = column_names(conn, "document_components")
    if "document_id" in cols:
        return
    conn.execute("ALTER TABLE document_components RENAME TO document_components_v040")
    conn.commit()

def ensure_v043_quality_schema(conn):
    if table_exists(conn, "procedures") and "confidence" not in column_names(conn, "procedures"):
        conn.execute("ALTER TABLE procedures ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0")
        conn.commit()

def table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None

def column_names(conn, name: str) -> set[str]:
    return {r["name"] for r in conn.execute(f'PRAGMA table_info("{name}")')}
