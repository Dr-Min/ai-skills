# Production-control maps

Use a production-control map when a video model repeatedly changes who occupies which part of the frame, flips an eyeline, crosses an axis, loses a planned occlusion, or collapses foreground/midground/background order. It is a generation-control derivative, not another storyboard and not a style reference.

## Trigger boundary

Do not create one for every shot. The normal storyboard panel and structured shot record are enough for a single static subject or simple action. Create a control packet when at least one of these is true:

- three or more independently staged subjects share a frame;
- subject and camera paths differ;
- a crossing, handoff, reveal, foreground wipe, or occlusion must occur in order;
- a dialogue scene must preserve seats, screen side, eyelines, and depth across many shots;
- the provider has already failed the same spatial relationship.

## Two-view contract

Create two distinct views from the same approved coordinates:

1. **Review view** — human-readable IDs, start/end marks, paths, gaze, camera side, depth order, occlusion, frame or time, and a color key outside the picture area.
2. **Clean model view** — flat color-coded shapes on a neutral field with no text, labels, arrows, facial detail, wardrobe, lighting, texture, or cinematic style. Use only the minimum geometry the model must preserve.

Declare that neutral field as `clean_map_background_color`. Every non-camera entity uses
its unique packet color, and the clean PNG may contain only the declared background and
entity colors with fully opaque or fully transparent pixels. The validator rejects any
other color, missing entity color, semitransparent edge, corrupt PNG, or crop mismatch.
This palette rule blocks photographic and anti-aliased artwork; human review still
checks that an allowed color was not arranged into text or decorative detail.

Never use the clean view as `IDENTITY`, `WARDROBE`, `STATE`, `LOCATION_GEOMETRY`, `MATERIAL_LIGHT`, `PROP_FUNCTION`, `STYLE`, `START`, or `END`. It conveys only shot structure and blocking. If the active provider cannot accept a dedicated structural input, translate the packet into the shot's spatial prompt block instead of mislabeling it as another role.

## Packet fields

For each shot, record:

- source plan path and SHA-256, shot ID, target aspect ratio, and exact frame range;
- normalized screen `x/y` and optional camera-relative depth for every start, waypoint, and end state;
- unique entity ID and color, subject count, body facing, gaze target, and occupied region;
- actor, prop, and camera paths as separate channels;
- axis side, entry/exit edges, contacts, handoffs, occlusions, and depth crossings;
- which coordinates were copied from approved records and which were inferred;
- failure conditions that make the map unusable.

Treat inferred positions as a review proposal. Show the review view and resolve disagreements before exporting a clean view.

Run the packet validator before handoff. It binds the exact source plan, shot frame range, aspect ratio, normalized coordinates, unique entity/color keys, clean-map palette, gaze and occlusion links, review/clean PNG paths, and actual SHA-256 bytes. A placeholder, path escape, missing file, stale hash, undeclared pixel color, or `structural_scope_only: false` is a hard failure.

## Depth assistance

A depth guide may express near/middle/far ordering or an approved depth raster when the active workflow can use it. It does not prove metric distance, hidden geometry, or camera calibration. Keep the exact crop and source frame hash. Reject it when silhouettes merge, body order is wrong, a cropped subject is invented in full, or the guide contradicts the approved plate.

## Handoff and QA

- Generate every revision from the same approved source plan or frame, not from the previous diagram.
- Change one spatial variable at a time and preserve source/derivative hashes.
- Count the clean map against the provider's verified reference budget.
- Prefer boundary frames, identity/state, and location evidence over an optional control map when the budget is tight.
- Inspect the resulting pixels and motion. A correct diagram is only an instruction, never proof that the generation followed it.
