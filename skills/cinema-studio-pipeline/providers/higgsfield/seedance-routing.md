# Higgsfield Seedance routing

Verify the active Seedance model, generation mode, reference limits, audio behavior,
duration, and quality in the current authenticated UI. Record the actual selections in
the take manifest even when they are omitted from prompt prose.

## Writer

Render only sections the shot needs, in this order:

```text
SCENE CONTEXT
ACTIVE REFERENCES
GEO SPATIAL LAYOUT
FIRST FRAME AND SPATIAL BLOCKING
FORMAT MODE
OPTICS
CAMERA
ACTION TIMING
PHYSICS
LIGHTING
AUDIO
CHARACTER ACTING
STYLE
QUALITY
POSITIVE CONSTRAINTS
```

Bind each active input to one role. Use the location for geography/materials, not its
accidental source framing. Keep current-shot context sealed.

When an approved rough storyboard exists and the current Seedance model supports
multimodal reference generation, use the original approved shot-relevant panel as an
optional structural reference for blocking, within-shot beat order, camera language, and
screen direction. Prefer this
for multi-character contact, threshold crossing, prop handoff, occlusion, or other
actions that text alone can spatially invert.

The board never changes `format_mode`. For `BOUNDARY_FRAME`, supply exact approved
`START`/`END`. For `REFERENCE_TEXT_NATIVE`, use role-specific assets without requiring a
finished start frame. Motion/audio modes keep their required inputs. Do not bind an
annotated board as `START`, `END`, `IDENTITY`, `WARDROBE`, `STATE`,
`LOCATION_GEOMETRY`, `MATERIAL_LIGHT`, `PROP_FUNCTION`, or `STYLE`; only a separately
approved clean derivative may serve as `STYLE`. Count all uploaded images against one
verified provider budget, prioritizing mode-required boundaries and identity/state/location
over the optional board. In the prompt, state that panel borders, labels, arrows, legends,
ghost silhouettes, graphite texture, and grayscale rendering are production annotations
and must not appear in the video.

## Auditor

Reject the prompt before generation when it contains an invented or stale tag,
unapproved asset, conflicting state, empty mode-required first frame, unclear left/right or
gaze, crossed axis, impossible timing, wrong-hand prop, lens/light contradiction,
dialogue ownership error, or a provider budget violation. Also reject a multimodal job
when a rough board is the only visual input for a photoreal shot, when an unapproved crop
or full contact sheet introduces unrelated panels, when the total provider reference
budget is exceeded, or when board annotations are not explicitly excluded from output
pixels.

## Workbench

Save the prompt as a versioned file. After a failed take, patch only the diagnosed
structured section, keep the rest constant, and record the exact change. If the same
failure survives controlled attempts, simplify the shot or return to the earliest
broken asset/contract.
