# Generation mode — BOUNDARY_FRAME

Use when both supplied start and end frames must match approved pixel states.

- Record exactly one `START` and one `END` item with boundary asset ID, path, SHA-256,
  and approval binding. Do not invent `@` tags for local boundary files.
- Begin on the approved start composition without an empty prelude.
- Define one physically causal bridge between boundaries.
- Preserve identity, geography, lighting logic, texture, wardrobe, and object state
  unless the contract explicitly changes them.
- Reach the end state only at the intended final beat; do not reveal it early.
- Inspect the actual final frames against the approved target before claiming a match.

Boundary mode is not the universal default. Return to native mode when exact boundary
pixels add constraints without a story or transition benefit.
