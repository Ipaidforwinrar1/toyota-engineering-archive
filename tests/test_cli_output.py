import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from cli import cmd_procedure
from database.db import apply_schema


ROOT = Path(__file__).resolve().parents[1]


class CliOutputTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(
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
                text_content TEXT
            );
            """
        )
        apply_schema(self.conn, ROOT / "database" / "schema_v0.4.3.sql")
        doc_id = self.conn.execute(
            """
            INSERT INTO documents(reference_id, document_uid, title, manual_type_normalized, system_name, section_path)
            VALUES('TEA-TEST', 'uid-1', 'INSTALLATION', 'Engine Repair Manual', 'Engine', 'FUEL / FUEL INJECTOR')
            """
        ).lastrowid
        component_id = self.conn.execute(
            """
            INSERT INTO components(canonical_name, normalized_name, system_name)
            VALUES('Fuel Injector', 'fuel injector', 'Fuel System')
            """
        ).lastrowid
        self.conn.execute(
            "INSERT INTO component_aliases(component_id, alias, normalized_alias) VALUES(?, 'Fuel Injector', 'fuel injector')",
            (component_id,),
        )
        self.conn.execute(
            """
            INSERT INTO procedures(component_id, document_id, page_number, procedure_type, title, context, step_count)
            VALUES(?, ?, 1, 'Installation', 'INSTALLATION', '1. INSTALL FUEL INJECTOR', 1)
            """,
            (component_id, doc_id),
        )
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_procedure_command_prints_document_and_page(self):
        args = SimpleNamespace(
            db=self.path,
            query="Fuel Injector",
            limit=5,
            type=None,
            doc_limit=5,
            context=False,
        )
        output = StringIO()

        with redirect_stdout(output):
            cmd_procedure(args)

        text = output.getvalue()
        self.assertIn("Fuel Injector", text)
        self.assertIn("Installation", text)
        self.assertIn("TEA-TEST", text)
        self.assertIn("page 1", text)


if __name__ == "__main__":
    unittest.main()
