import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.db import apply_schema


ROOT = Path(__file__).resolve().parents[1]


def make_connection():
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    path = Path(handle.name)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_id TEXT NOT NULL UNIQUE,
            document_uid TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            manual_type_normalized TEXT,
            system_name TEXT,
            section_path TEXT
        );

        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            text_content TEXT,
            UNIQUE(document_id, page_number),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        """
    )
    apply_schema(conn, ROOT / "database" / "schema_v0.4.3.sql")
    return conn, path


class DatabaseIntegrityTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "conn"):
            self.conn.close()
        if hasattr(self, "path"):
            self.path.unlink(missing_ok=True)

    def test_document_components_prevent_duplicate_page_component_rows(self):
        self.conn, self.path = make_connection()
        document_id = self.conn.execute(
            "INSERT INTO documents(reference_id, document_uid, title) VALUES('TEA-TEST', 'uid-1', 'REMOVAL')"
        ).lastrowid
        component_id = self.conn.execute(
            "INSERT INTO components(canonical_name, normalized_name) VALUES('Fuel Injector', 'fuel injector')"
        ).lastrowid

        self.conn.execute(
            """
            INSERT INTO document_components(document_id, reference_id, component_id, page_number)
            VALUES(?, 'TEA-TEST', ?, 1)
            """,
            (document_id, component_id),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO document_components(document_id, reference_id, component_id, page_number)
                VALUES(?, 'TEA-TEST', ?, 1)
                """,
                (document_id, component_id),
            )

    def test_procedures_are_foreign_key_clean(self):
        self.conn, self.path = make_connection()
        document_id = self.conn.execute(
            "INSERT INTO documents(reference_id, document_uid, title) VALUES('TEA-TEST', 'uid-1', 'INSTALLATION')"
        ).lastrowid
        component_id = self.conn.execute(
            "INSERT INTO components(canonical_name, normalized_name) VALUES('Fuel Injector', 'fuel injector')"
        ).lastrowid

        self.conn.execute(
            """
            INSERT INTO procedures(component_id, document_id, page_number, procedure_type, title, context, step_count)
            VALUES(?, ?, 1, 'Installation', 'INSTALLATION', '1. INSTALL FUEL INJECTOR', 1)
            """,
            (component_id, document_id),
        )

        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_component_quality_marks_generic_components(self):
        self.conn, self.path = make_connection()
        component_id = self.conn.execute(
            "INSERT INTO components(canonical_name, normalized_name) VALUES('Connector', 'connector')"
        ).lastrowid

        self.conn.execute(
            """
            INSERT INTO component_quality(component_id, is_generic, quality_weight, notes)
            VALUES(?, 1, 0.2, 'generic electrical term')
            """,
            (component_id,),
        )

        row = self.conn.execute(
            "SELECT is_generic, quality_weight FROM component_quality WHERE component_id=?",
            (component_id,),
        ).fetchone()
        self.assertEqual(row["is_generic"], 1)
        self.assertEqual(row["quality_weight"], 0.2)


if __name__ == "__main__":
    unittest.main()
