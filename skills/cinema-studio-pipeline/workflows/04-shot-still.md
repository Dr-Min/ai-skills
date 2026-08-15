# 04 — Shot card and still

Lock the shot's story, edit, spatial, and reference contract before video generation.

## Shot card

Create `shot.json` from `templates/SHOT_CARD.json`. Resolve:

- story purpose and edit purpose;
- duration or usable duration range;
- generation mode;
- exact active asset IDs, states, and reference roles;
- scene geography, axis, first-frame occupancy, and screen direction;
- shot size, camera side, observable optics, movement, and focus;
- timed action, physics, light, acting, dialogue, ambience, and cut intent;
- for every dialogue line, an exact `voice_asset_id` that resolves to the approved
  `VOICE` asset active in the `AUDIO` role;
- known local failure locks;
- source story, board, look, and asset approval hashes.

Store them in `dependency_snapshot.{story,storyboard,lookdev,required_assets}`. Every
binding carries `subject_type`, `subject_id`, `approval_id`, `USER_APPROVED`, exact
`subject_sha256`, `authority_path`, and `approval_record_path`; asset bindings also
carry `asset_id`. Copy the exact `storyboard_panel_ids`, `coverage_requirement_ids`,
and complete `required_asset_ids` set from the approved `storyboard.shot_plan`. Changed
bytes under a reused ID are stale.

Run `scripts/validate_references.py` before generation. Fail on stale tags, unapproved
inputs, missing roles, conflicting state controllers, or an invalid reference budget.

## Still evidence contract

Record visible evidence in `shot.still_evidence`; a prompt, filename, or `shot.json`
alone is not pixel proof.

- For non-`BOUNDARY_FRAME` modes, record exactly one item with role
  `STILL`, project-relative path, and SHA-256. Keep the required `asset_id` key; use
  `null` when the generated review still is not itself an asset authority record.
- For `BOUNDARY_FRAME`, record the structural `START` and `END` items that are present
  in `boundary_frames`. Their asset IDs, paths, and hashes must match the current
  `USER_APPROVED` boundary assets exactly. Do not duplicate a role or path.
- When a central approval targets a shot as `USER_REVIEW_REQUIRED` or `USER_APPROVED`,
  the shot must contain real evidence whose bytes match every declared hash. An
  unreviewed starter may keep an empty evidence list.
- When `spatial.control_packet` is present, validate it with timed-storyboard first.
  The packet and its hash-bound review/clean map outputs become mandatory SHOT_STILL
  approval evidence; a missing or changed packet/map blocks the decision.

Check identity, wardrobe, anatomy, geography, light, materials, contact, and intended
crop. Do not repair a foundational location or character error downstream.

## Gate

Complete `shot.json` without top-level approval state, then hash it. Before review,
copy identical bytes to `05_shots/<shot-id>/history/vNNN/shot.json` and mirror every
visible still/boundary file below that version's `evidence/<project-relative-path>`.
The central `09_approvals/<approval-id>.json` subject targets the exact current shot hash;
its evidence contains current/archive pairs for `shot.json` and every visible pixel file.
Set that approval to `USER_REVIEW_REQUIRED`, show the pixels, and stop. Approval changes
only the central record; never rewrite the shown shot bytes. Advance only when the
current shot and pixels have an exact central `USER_APPROVED` decision.
For a multi-shot project, repeat this per included shot. The collection gate closes
only when every required shot in the approved shot plan has a current centrally approved record;
extra candidates must have a terminal central decision: `REJECTED`, `SUPERSEDED`, or
`EXCLUDED_FROM_INPUTS`. A rejected shot keeps its history bytes and `REJECTED` decision
when a successor is linked. Changing any snapshot dependency invalidates this shot and its downstream records according to
`references/12-invalidation-and-revisions.md`.
