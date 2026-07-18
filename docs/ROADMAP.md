# Roadmap

## Complete

- v0.3: PDF Archive
- v0.4.1: Component Knowledge Base
- v0.4.2: Procedure Knowledge Base

## Next

### v0.4.3: Engineering Specifications

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
