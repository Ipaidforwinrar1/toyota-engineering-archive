import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.db import apply_schema
from knowledge.api import KnowledgeBase


ROOT = Path(__file__).resolve().parents[1]


class KnowledgeApiTests(unittest.TestCase):
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
            VALUES('TEA-TEST', 'uid-1', 'REMOVAL', 'Engine Repair Manual', 'Engine', 'FUEL / INJECTOR')
            """
        ).lastrowid
        second_doc_id = self.conn.execute(
            """
            INSERT INTO documents(reference_id, document_uid, title, manual_type_normalized, system_name, section_path)
            VALUES('TEA-SECOND', 'uid-2', 'INSTALLATION', 'Engine Repair Manual', 'Engine', 'FUEL / INJECTOR')
            """
        ).lastrowid
        component_id = self.conn.execute(
            """
            INSERT INTO components(canonical_name, normalized_name, system_name)
            VALUES('Fuel Injector', 'fuel injector', 'Fuel System')
            """
        ).lastrowid
        self.conn.execute(
            "INSERT INTO component_aliases(component_id, alias, normalized_alias) VALUES(?, 'Injector', 'injector')",
            (component_id,),
        )
        self.conn.execute(
            "INSERT INTO component_aliases(component_id, alias, normalized_alias) VALUES(?, 'Fuel Injector', 'fuel injector')",
            (component_id,),
        )
        self.conn.execute(
            """
            INSERT INTO document_components(
                document_id, reference_id, component_id, page_number,
                occurrence_count, confidence, first_context
            )
            VALUES(?, 'TEA-TEST', ?, 1, 2, 0.95, 'Remove the injector.')
            """,
            (doc_id, component_id),
        )
        self.conn.execute(
            """
            INSERT INTO document_components(
                document_id, reference_id, component_id, page_number,
                occurrence_count, confidence, first_context
            )
            VALUES(?, 'TEA-SECOND', ?, 1, 10, 0.30, 'Mentioned in a note.')
            """,
            (second_doc_id, component_id),
        )
        self.conn.execute(
            """
            INSERT INTO procedures(
                component_id, document_id, page_number, procedure_type,
                title, context, step_count, confidence
            )
            VALUES(?, ?, 1, 'Removal', 'REMOVAL', '1. REMOVE INJECTOR', 1, 0.9)
            """,
            (component_id, doc_id),
        )
        self.conn.execute(
            """
            INSERT INTO procedures(
                component_id, document_id, page_number, procedure_type,
                title, context, step_count, confidence
            )
            VALUES(?, ?, 1, 'Removal', 'REMOVAL', '1. REMOVE FROM NOTE', 4, 0.3)
            """,
            (component_id, second_doc_id),
        )
        second_component_id = self.conn.execute(
            """
            INSERT INTO components(canonical_name, normalized_name, system_name)
            VALUES('Injector Driver', 'injector driver', 'Engine Control')
            """
        ).lastrowid
        self.conn.execute(
            "INSERT INTO component_aliases(component_id, alias, normalized_alias) VALUES(?, 'Injector Driver', 'injector driver')",
            (second_component_id,),
        )
        self.conn.execute(
            """
            INSERT INTO document_components(
                document_id, reference_id, component_id, page_number,
                occurrence_count, confidence, first_context
            )
            VALUES(?, 'TEA-SECOND', ?, 1, 1, 0.4, 'Injector driver mention.')
            """,
            (second_doc_id, second_component_id),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.path.unlink(missing_ok=True)

    def test_get_component_returns_unified_object(self):
        item = KnowledgeBase(self.conn).get_component("Injector")

        self.assertEqual(item.api_version, "0.4.4")
        self.assertEqual(item.component.canonical_name, "Fuel Injector")
        self.assertEqual(item.aliases, ("Fuel Injector", "Injector"))
        self.assertEqual(item.statistics["document_count"], 2)
        self.assertEqual(item.documents[0].reference_id, "TEA-TEST")
        self.assertGreater(item.documents[0].confidence, item.documents[1].confidence)
        self.assertEqual(item.procedures[0].procedure_type, "Removal")
        self.assertGreater(item.procedures[0].confidence, item.procedures[1].confidence)
        self.assertEqual(item.procedure_counts, (("Removal", 2),))

    def test_missing_component_returns_none(self):
        self.assertIsNone(KnowledgeBase(self.conn).get_component("No Such Part"))

    def test_ambiguous_alias_resolves_to_highest_ranked_component(self):
        item = KnowledgeBase(self.conn).get_component("Injector")

        self.assertEqual(item.component.canonical_name, "Fuel Injector")

    def test_connection_is_owned_by_caller(self):
        kb = KnowledgeBase(self.conn)
        self.assertIsNotNone(kb.get_component("Injector"))

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM components").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
