# 08 — Multi-scene and feature production system

Use this module when the work spans many scenes, multiple operators, a long runtime,
or enough assets that memory and ad-hoc filenames are unsafe. Keep the core pipeline
gates; expand the records underneath them.

## Contents

- Authoritative production records
- Asset lock gate
- Scene production loop
- Scale and complexity patterns
- Approval gates

## Authoritative production records

Maintain one source of truth for each layer. Use the v2 schemas and project-relative
records; Markdown may explain a decision but does not override JSON authority:

- **Story brief** — cause, goal, stakes, obstacle, discovery, choice, and required
  continuity.
- **Project-wide storyboard** — `story_dependency` binds the approved story;
  `asset_plan` owns every planned production asset; `scenes[].panels` owns geography,
  action/camera paths, and hashed panel images.
- **Authoritative shot and coverage plan** — `shot_plan` owns every required shot,
  panel link, asset need, coverage ID, and minimum approved-take count. Shot/take
  records execute this inventory and never silently expand it.
- **Approved asset records** — each planned asset resolves to a versioned `asset.json`
  with actual `@` tag, descriptor, state, source master, stress-test verdict, and approval.
- **Constants** — approved descriptors, voice descriptors, and project-specific style
  wrappers. Edit a constant once; do not hand-copy divergent variants.

Split the film into scene blocks in story order. Assign responsibility by block when a
team is involved, but keep the registries and naming contract shared across the film.
Memory may help recall decisions; the current project-wide storyboard and authority
records decide what is authoritative.

## Asset lock gate

Treat an asset as `descriptor + reference`, not as an image alone. Copy the approved
descriptor word for word into every prompt that uses the asset.

Before locking a character:

1. Test at least 10 useful variations across pose, distance, and lighting.
2. Test beside the other active characters.
3. Test in the actual location and light planned for the film.
4. Require recognizability and critical anchors to hold in every approved test.
5. Rewrite the descriptor or rebuild the source if the same feature fails repeatedly.

Create separate assets and descriptors for materially different states: dry/wet,
clean/bloodied, wardrobe A/B, intact/damaged, day/night/rain, prop visible/hidden, or
other changes that the model might mix. Do not put mutually exclusive states in one
descriptor.

Lock voices before dialogue production. Store register, tempo, accent, manner, and
pronunciation as a fixed voice descriptor, then stress-test it across generations.

ASSET_LOCK closes only when every current `asset_plan` item has one matching approved
record and every extra candidate has a terminal exclusion/replacement status.

## Scene production loop

For each scene block:

1. Lock assets and descriptors.
2. Lock the pure geography map and camera-side rule.
3. For a difficult ensemble, lock the seat/mark/eyeline/depth ledger and derive one
   clean geometry-only control map from the approved storyboard coordinates.
4. Prepare shot records in `shot_plan` order, copying exact panel/coverage IDs and the
   current story/board/look/asset approval snapshot.
5. Generate in batches small enough to review while context is fresh.
6. In `ASSEMBLY_WHILE_GENERATING`, assemble approved usable shots and let the edit
   request missing wides, inserts, reaction shots, and cutaways. In
   `RAW_SOURCE_FIRST`, keep building the approved source library without creative
   timeline work.
7. Change one prompt line per diagnostic iteration and log the result.

Use this minimum iteration record:

```text
shot: [ID]
prompt_version: [V#]
changed_line: [one exact change]
kept_constant: [assets, geography, camera, timing, or other controls]
result: [observable outcome]
verdict: [PASS / SOURCE_ASSET_FAILURE / DIRECTION_FAILURE / MODEL_FAILURE / INCONCLUSIVE]
next_action: [one action]
```

After 10–15 controlled attempts, stop polishing wording. Split the shot, remove an
action, reduce the active space, change the angle, or replace the failing source.

## Scale and complexity patterns

- **Complex action** — open already in the important action state. Put the approach or
  wind-up in a separate shot.
- **Crowd** — use one crowd reference describing the range of heights and wardrobe;
  give only close-up lead extras separate assets. State the required visible count.
- **Space transition** — hold both location references at a doorway, arch, lift, or
  other threshold. Use a motivated light or palette contrast across the seam.
- **Giant scale** — repeat exact size plus two visible comparisons: a human scale
  anchor and a framing consequence. Define a visible failure condition.
- **Static dialogue** — stage it in one constrained corner instead of an entire room.

## Gate closure at scale

- STORYBOARD binds its JSON and every panel image through central evidence.
- ASSET_LOCK resolves every `asset_plan` item with a record whose exact master has a
  current central `USER_APPROVED` ASSET decision.
- SHOT_STILL resolves every `shot_plan` item with an approved shot and still evidence.
- RAW_VIDEO satisfies every `coverage_requirements.minimum_approved_takes`; all other
  take candidates are `REJECTED`, `SUPERSEDED`, or `EXCLUDED_FROM_INPUTS` explicitly.
- SOURCE_LIBRARY locks only approved immutable sources; EDIT uses only that library.
- EDIT content declares `PICTURE_LOCKED` before review; only a central EDIT approval
  targeting those exact bytes makes it effective. FINISH binds a separate delivery
  record whose `media_integrity` passes and whose master/QA bytes are evidenced.

Every approval record lives in `09_approvals/` and targets the exact current subject
hash. Use `references/12-invalidation-and-revisions.md` when any authority changes.

Do not claim that a remote project, folder, Element, or generation exists until the
actual service state is visible and verified.
