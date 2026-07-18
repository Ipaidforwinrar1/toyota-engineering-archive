# v0.4.2 Procedure Extraction Audit

Audit date: 2026-07-18

Database audited: `toyota_archive_v0.4.2.db`

## Method

Reviewed 30 deterministic sample procedure records from the `procedures` table, joined to `components` and `documents`.

Sample query:

```sql
SELECT p.procedure_id,
       c.canonical_name,
       p.procedure_type,
       d.title,
       d.reference_id,
       p.page_number,
       p.step_count,
       substr(p.context,1,180) AS snippet
FROM procedures p
JOIN components c USING(component_id)
JOIN documents d ON d.id=p.document_id
ORDER BY ((p.procedure_id * 37) % 997)
LIMIT 30;
```

## Summary

- Procedure heading detection is useful and generally lands on real Toyota manual procedure blocks.
- Block boundaries are good enough for v0.4.2: procedure text usually starts at the expected heading or continuation page.
- Step counts now work on flattened OCR text such as `1. INSTALL... 2. CONNECT...`.
- The main quality issue is component association, not procedure block detection.

## Good Examples

- `Fuel Injector` procedures include Inspection, Installation, and Removal.
- `Valve Body` procedures include Disassembly and Reassembly.
- `Camshaft Position Sensor` Disassembly produced a clean numbered procedure.
- `Brake Master Cylinder` Removal produced a clean numbered procedure.
- `Intake Manifold` Removal produced a long, plausible removal sequence.

## Known Issues

- Generic components create noisy links:
  - `Connector`
  - `Battery`
  - `Starter`
- Some components are linked because they appear in prerequisite or warning text, not because the procedure is primarily about that component.
- Multi-page continuation procedures can link components that appear only on one continuation page.
- OCR artifacts remain in context text, especially punctuation and minus symbols.
- Procedures are stored as page-level blocks. Individual steps are counted but not yet normalized into separate rows.

## Recommendation Before v0.4.3

- Keep v0.4.2 as stable.
- Use `toyota_archive_working.db` for experiments.
- Add a confidence or role field later for procedure-component links:
  - primary subject
  - mentioned part
  - prerequisite part
  - warning/safety mention
- Consider down-weighting very generic aliases like `connector` unless the document section/title also supports the component association.
