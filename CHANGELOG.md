# Changelog

## v0.4.2 - Procedure Knowledge Base

Release date: 2026-07-18

### Added

- Added a `procedures` table linked to `components` and `documents`.
- Added procedure extraction for:
  - Removal
  - Installation
  - Disassembly
  - Reassembly
  - Inspection
  - Adjustment
  - Replacement
- Added `extract-procedures` CLI command.
- Added `procedure "<component>"` CLI command for component procedure lookup.
- Added `component "<component>" --procedures` summary view.
- Added step-count detection for flattened OCR procedure text.
- Added v0.4.2 schema file at `database/schema_v0.4.2.sql`.

### Changed

- Updated the application version from v0.4.1 to v0.4.2.
- Updated `stats` output to include procedure totals.
- Updated README and quick start documentation with procedure workflows.

### v0.4.1 Foundation Included

- Component and alias dictionaries.
- Component extraction from `pdf_pages` joined to `documents`.
- Component occurrence storage by `document_id`, page, and component.
- Human-readable component search output with document title, TEA reference, category, section, page, and context.
- Idempotent component extraction reporting with inserted, existing, and updated row counts.

### Verification

- Source database preserved: `toyota_archive_v0.3.db`.
- Stable release database snapshot: `toyota_archive_v0.4.2.db`.
- Component rows: 5,091.
- Documents represented by component rows: 1,134.
- Total component occurrences: 12,949.
- Procedure records: 837.
- Components with procedures: 50.
- Procedure blocks detected during full extraction: 856.
- Second `extract-procedures` run inserted 0 rows and updated 0 rows.
- `PRAGMA foreign_key_check` returned no violations.

### Notes

- Procedures are stored as page-level text blocks in v0.4.2.
- Individual procedure steps are counted but not yet stored as separate rows.
- Future versions can add normalized procedure steps, engineering relationships, and specifications.
