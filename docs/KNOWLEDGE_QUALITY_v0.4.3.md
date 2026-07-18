# v0.4.3 Knowledge Quality

v0.4.3 improves the usefulness of the existing component and procedure layers before adding new extraction domains.

## Goals

- Reduce noisy component associations.
- Keep generic components searchable without letting them dominate rankings.
- Store confidence scores directly on extracted knowledge rows.
- Preserve the original v0.4.2 database snapshot and run experiments on `toyota_archive_working.db`.

## Generic Components

Generic component metadata lives in:

```text
data/generic_components.csv
```

Current generic/downweighted components:

- Battery
- Connector
- Fuse
- Relay
- Starter

## Confidence

Component confidence is based on:

- Whether the component appears in the document title.
- Whether it appears in the section path.
- Whether it appears near the extracted context.
- Whether a component alias appears in those fields.
- Mention count on the page/procedure block.
- Generic component quality weight.

The score is stored in:

- `document_components.confidence`
- `procedures.confidence`

## Search Ranking

Component search now reports:

- raw document count
- raw occurrence count
- confidence-weighted score
- average confidence
- generic marker

This keeps raw evidence visible while making noisy matches easier to spot.
