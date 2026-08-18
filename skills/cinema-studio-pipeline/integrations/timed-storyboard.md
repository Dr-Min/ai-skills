# Handoff to timed-storyboard

Keep storyboard design independent from music-transient analysis.

## Input contract

- approved story-contract ID and hash;
- target runtime or rough range;
- user-selected roughness level;
- world/character constraints and existing approved references;
- required action, camera, gaze, and spatial paths.

Invoke the separate `timed-storyboard` skill. Do not let it generate final cinematic
stills or videos automatically.

## Output contract

Require one project-wide `storyboard.json`: `story_dependency`; nonempty `asset_plan`;
`scenes[].panels` with action/camera paths, duration hints, `image_file`, and
`image_sha256`; and `shot_plan[].coverage_requirements` with minimum approved-take
counts. Make IDs globally unique and resolve panel/shot asset IDs to `asset_plan`.
For review-ready and approved boards, require every scene ID to be referenced by at
least one shot-plan item; this semantic scene-to-shot closure is validator-enforced.
Before the central approval enters `USER_REVIEW_REQUIRED`, copy the board to
`02_storyboard/history/<storyboard-id>/vNNN/storyboard.json` and mirror every panel and
file-backed story prerequisite under that version's
`evidence/<project-relative-path>`. Central evidence contains equal-hash current/archive
pairs for the board and every supporting file. `storyboard.json` carries no local
approval state and stays byte-identical through the decision. Show the complete inventory
and every panel, then stop. Import only that evidenced version after user approval.

Storyboard duration is a planning hint. Actual cut frames belong to `timeline.json`.

## Optional production-control export

For multi-character staging, crossings, eyelines, occlusion, or depth order that a
normal panel does not communicate reliably, use `timed-storyboard`'s
`references/production-control-maps.md`. Derive a labeled human review map and a clean
geometry-only map from the approved plan coordinates. Bind the packet and map hashes as
supporting review evidence; never treat them as a new approval authority or a new shot
generation mode.

After the timed-storyboard validator passes, set `shot.spatial.control_packet` to the
packet's project-relative path and SHA-256. `prepare_review.py` and
`record_decision.py` then collect the packet plus its review/clean map bytes as mandatory
SHOT_STILL evidence. A missing or changed packet/map blocks the decision and changing
the binding changes the shot authority hash.

The clean map controls only occupied regions, paths, gaze, camera side, depth, and
occlusion. It must not carry text, arrows, faces, wardrobe, location materials,
lighting, or style. The validator enforces the declared flat background/entity palette;
human review still rejects text or shapes drawn with an otherwise allowed color. If the provider lacks a dedicated structural input, translate the
approved packet into `FIRST_FRAME_AND_SPATIAL_BLOCKING` instead of assigning a false
reference role.

## Seedance multimodal handoff

When the active Seedance route supports multimodal reference generation, pass the
approved shot-relevant storyboard panel or micro-board as a structural direction input
when it makes action order, framing, camera movement, screen direction, or geography
more reliable. This is preferred over describing complex blocking from text alone.

Assign the annotated board only these roles: shot structure, blocking, within-shot action
progression, camera language, and continuity. It can never be the first/end-frame pixel
contract, character identity, wardrobe/state, location geometry, material/light, or
prop-function reference. Only a separately exported clean derivative with its own approval
may become a `STYLE` reference.

Apply companions by the shot's already-selected `format_mode`:

- `BOUNDARY_FRAME`: pair the structural board with exact approved `START` and `END` frames;
- `REFERENCE_TEXT_NATIVE`: use the structural board with approved role-specific assets;
  do not require a finished start or boundary frame;
- `MOTION_REFERENCE` and `MUSIC_LIPSYNC`: retain their required motion/audio inputs; the
  optional board does not change or combine generation modes;
- for every mode, include only the character, wardrobe/state, location, material/light,
  and prop references actually required by the shot;
- a prompt that says to preserve the board's staging while excluding panel borders,
  captions, arrows, legends, ghost figures, graphite lines, and grayscale board style.

Do not upload an entire project-wide contact sheet when only one shot is being generated.
Until an exact structural-reference path/hash binding exists in the schema, use only the
original approved panel bytes; do not make an ad hoc crop or micro-board. More visible
details create more activation pressure. Count the board, boundary frames, and every
role-specific image against one verified provider limit. Required mode inputs, identity,
state, and location outrank the optional board when the budget is tight.
