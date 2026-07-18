import unittest

from extractors.component_extractor import compile_patterns, extract_components
from extractors.procedure_extractor import extract_procedure_blocks


class ComponentExtractorTests(unittest.TestCase):
    def test_alias_matching_prefers_longer_non_overlapping_aliases(self):
        patterns = compile_patterns([
            (1, "Fuel Injector", "injector"),
            (1, "Fuel Injector", "fuel injector"),
            (2, "Fuel Pump", "fuel pump"),
        ])

        mentions = extract_components("Remove the fuel injector and inspect the fuel pump.", patterns)

        by_name = {m.canonical_name: m for m in mentions}
        self.assertEqual(by_name["Fuel Injector"].count, 1)
        self.assertEqual(by_name["Fuel Pump"].count, 1)

    def test_alias_matching_handles_punctuation_between_tokens(self):
        patterns = compile_patterns([(1, "O-ring", "O ring")])

        mentions = extract_components("Replace the O-ring before installation.", patterns)

        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].canonical_name, "O-ring")


class ProcedureExtractorTests(unittest.TestCase):
    def test_detects_multiple_toyota_procedure_headings(self):
        text = """REMOVAL
1. REMOVE FUEL INJECTOR
2. REMOVE O-RING

INSPECTION
1. INSPECT RESISTANCE

INSTALLATION
1. INSTALL O-RING
2. INSTALL FUEL INJECTOR
"""

        blocks = extract_procedure_blocks(text, document_title="Fuel Injector")

        self.assertEqual([b.procedure_type for b in blocks], ["Removal", "Inspection", "Installation"])
        self.assertEqual([b.step_count for b in blocks], [2, 1, 2])

    def test_uses_document_title_when_page_has_no_standalone_heading(self):
        blocks = extract_procedure_blocks(
            "1. REMOVE FUEL INJECTOR\n2. REMOVE O-RING",
            document_title="REMOVAL",
            section_path="FUEL / FUEL INJECTOR",
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].procedure_type, "Removal")
        self.assertIn("FUEL INJECTOR", blocks[0].title)
        self.assertEqual(blocks[0].step_count, 2)


if __name__ == "__main__":
    unittest.main()
