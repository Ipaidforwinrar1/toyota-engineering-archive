# Toyota Engineering Archive v0.4.2

This release adds data-driven **Component** and **Procedure** knowledge bases to the existing v0.3 archive.

## Features

- Non-destructive SQLite migration
- Component and alias dictionaries
- Native v0.3 catalog support using `documents.id -> pdf_pages.document_id`
- Rule-based component extraction
- Page/document occurrence indexing with document title, reference, category, and section metadata
- Procedure extraction for Removal, Installation, Disassembly, Reassembly, Inspection, Adjustment, and Replacement
- Component search with optional context
- Procedure search by component
- Extraction history and statistics

## Quick start

```powershell
Copy-Item .\toyota_archive_v0.3.db .\toyota_archive_v0.4.db

py .\cli.py --db .\toyota_archive_v0.4.db init

py .\cli.py --db .\toyota_archive_v0.4.db detect-source

py .\cli.py --db .\toyota_archive_v0.4.db extract-components --limit 20

py .\cli.py --db .\toyota_archive_v0.4.db component "ACIS" --details --context

py .\cli.py --db .\toyota_archive_v0.4.db extract-procedures --limit 100

py .\cli.py --db .\toyota_archive_v0.4.db procedure "Fuel Injector"
```

## Tests

```powershell
py -m unittest discover -v
```

The test suite covers procedure heading detection, component alias matching,
duplicate protection, foreign-key integrity, and CLI procedure output.

After the test:

```powershell
py .\cli.py --db .\toyota_archive_v0.4.db extract-components --rebuild
py .\cli.py --db .\toyota_archive_v0.4.db stats
```

The extractor reads text already stored in SQLite. It does not reopen all PDFs.
For the real v0.3 database, extraction reads `pdf_pages` joined to `documents` and stores
component and procedure hits by `document_id`.

## Dictionary editing

Edit:

- `data/components.csv`
- `data/aliases.csv`

Then rerun `init` and rebuild extraction.

## Compatibility note

v0.4.2 is designed around the real v0.3 SQLite schema. `detect-source` should report
`pdf_pages JOIN documents` when the v0.3 tables are present.
