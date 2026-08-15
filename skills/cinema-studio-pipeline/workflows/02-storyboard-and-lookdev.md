# 02 — Timed storyboard and look development

Translate the approved story contract into readable action, space, and visual intent.
Do not combine this gate with music-transient detection.

## Inputs

- approved story contract and hash;
- runtime or rough duration range;
- user-selected storyboard roughness level;
- existing characters, references, or design constraints.

## Project-wide storyboard and coverage plan

Use `integrations/timed-storyboard.md` when a board is needed. `storyboard.json` is the
authoritative inventory for the whole project, not one scene. DRAFT may keep
`asset_plan`, `scenes`, and `shot_plan` empty. In `scenes[].panels`, record:

- story beat and why the cut or continuation exists;
- action at the beginning and end of the panel;
- body, gaze, object, and camera paths;
- rough duration as a hint, not false frame precision;
- shot size, angle, lens result, movement, and depth planes;
- geography and relation to adjacent panels;
- performance change and residual emotion;
- audio intention, without beat-forcing the story.

For difficult ensemble blocking, also derive the optional review/clean
production-control pair described in `integrations/timed-storyboard.md`. It stays a
supporting derivative of the approved panel coordinates, not a second blocking truth.

Bind `story_dependency` to the exact current story `approval_id`, path, and SHA-256.
When a central approval first targets the board as `USER_REVIEW_REQUIRED`, every panel
requires `image_file` and `image_sha256`; verify those bytes.
The LOOKDEV approval evidence likewise includes the current storyboard path and hash.

In `asset_plan`, add at least one `{asset_id, kind, state_label, purpose}` item and name
every character, state, location, prop, motion, style, or audio asset that Asset lock
must resolve. These are planned requirements; do not pretend final assets are approved.

In `shot_plan`, enumerate every required shot before collection gates can close. Bind
each item to its scene and panel IDs, list `required_asset_ids` from `asset_plan`, and
define `coverage_requirements` with unique IDs and `minimum_approved_takes >= 1`. An
approved/review-ready board must map every `scenes[].scene_id` to at least one
`shot_plan[]` item. An omitted asset, scene coverage, or shot is not silently inferred
later; revise and reapprove the board.

Generate rough storyboard panels with the image-generation route when visual proof is
needed. Record every panel image path and SHA-256. The storyboard approval evidence
includes the complete `storyboard.json` plus every panel image; changing a panel
invalidates the approval. Show the complete scene/asset/shot/coverage inventory with
the board and stop for approval before producing final concept frames.

Before central review, copy identical board bytes to
`02_storyboard/history/<storyboard-id>/vNNN/storyboard.json`. Mirror every panel and
file-backed story prerequisite below that version's
`evidence/<project-relative-path>`. The approval evidence contains current/archive
pairs with equal hashes for the board and every supporting file. Do not add local
`review_status` or `approval_id` fields to `storyboard.json`.

## Look and mise-en-scene

Fill `templates/VISUAL_BIBLE.md` after the board direction is approved. Lock world/era,
materials, motivated light, palette hierarchy, lens grammar, texture, recurring
motifs, public/private visual contrast, and deliberate exceptions. A style word is
not a visual bible. Before look review, copy identical bytes to
`03_lookdev/history/visual-bible/vNNN/VISUAL_BIBLE.md`; mirror its current storyboard,
panel, and other file evidence below that version's `evidence/<project-relative-path>`.

## Output and gate

Save `storyboard.json` and panel files in `02_storyboard/`, and the visual bible in
`03_lookdev/`. Save every approval record only in the canonical `09_approvals/`
directory. Use the current storyboard ID for its approval and the stable subject ID
`visual-bible` for the visual-bible Markdown. Advance only when central `USER_APPROVED`
records target both exact current artifact hashes. Allocate the next unused zero-padded
review version before the central approval enters `USER_REVIEW_REQUIRED`; never mutate
a content authority or snapshot after hashing it for review. Reapproval of either fixed current
path uses the reciprocal fixed-authority replacement protocol. A story, board JSON,
panel image, asset plan, or shot-plan change follows the reset matrix in
`references/12-invalidation-and-revisions.md`.
