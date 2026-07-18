# Roadmap

## Complete

- v0.3: PDF Archive
- v0.4.1: Component Knowledge Base
- v0.4.2: Procedure Knowledge Base

## Next

### v0.4.3: Knowledge Quality

Improve the signal quality before adding another extraction layer.

Initial quality controls:

- Generic component metadata.
- Component confidence scores.
- Confidence-weighted component ranking.
- Audit low-confidence and noisy associations.

### v0.4.4: Engineering Specifications

First introduce a unified knowledge API so future CLI, web, REST, and assistant interfaces do not query schema tables directly.

Start with preserved original text before aggressive normalization.

Initial specification types:

- Torque
- Resistance
- Voltage
- Pressure
- Clearance
- Capacity
- Temperature

Suggested first schema:

- `component_id`
- `document_id`
- `page_number`
- `specification_type`
- `value_text`
- `unit`
- `context`

### Later

- Normalize individual procedure steps.
- Extract engineering relationships.
- Build semantic engineering search.
