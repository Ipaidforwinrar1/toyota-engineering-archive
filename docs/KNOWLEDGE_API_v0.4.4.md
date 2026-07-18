# v0.4.4 Unified Knowledge API

v0.4.4 introduces an application-facing API layer over the SQLite schema.

The goal is to let interfaces ask for knowledge objects instead of composing SQL joins directly.

## Current Entry Point

```python
from database.db import connect
from knowledge.api import KnowledgeBase

conn = connect("toyota_archive_working.db")
kb = KnowledgeBase(conn)
item = kb.get_component("Fuel Injector")
```

## Version

Every `ComponentKnowledge` result exposes:

```python
item.api_version == "0.4.4"
```

## Behavior Contract

- Missing components return `None`.
- Ambiguous component queries resolve to the highest-ranked component from `search_components()`.
- Aliases are returned in deterministic case-insensitive order.
- Documents are ordered by confidence, occurrence count, reference, and page.
- Procedures are ordered by procedure type, confidence, step count, reference, and page.
- `KnowledgeBase` does not close connections supplied by the caller. The caller owns connection lifetime.

## Component Knowledge Object

`get_component()` returns a `ComponentKnowledge` object with:

- `component`
- `aliases`
- `quality`
- `documents`
- `procedures`
- `procedure_counts`
- `statistics`
- `related_items`

`related_items` is intentionally empty for now. It is reserved for future relationship extraction.

## Consumers

The CLI now uses this API for:

- `component`
- `procedure`

Future consumers can use the same API:

- web UI
- REST API
- AI assistant
- reports/export tools
