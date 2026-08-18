# 05 — Raw video generation

Generate one diagnosable source clip from an approved shot contract.

## Preflight

1. Validate project, shot, approvals, references, roles, and hashes.
2. Verify live provider capabilities and UI settings; record them outside the prompt.
3. Load the selected generation-mode workflow.
4. When the approved shot requires exact ensemble staging, verify the optional
   production-control packet/map hash and provider input budget; otherwise omit it.
5. Render the Seedance prompt from `shot.json` using
   `references/09-seedance-prompt-director.md` and acting rules when needed.
6. Audit first-frame occupancy, stale tags, geography, lens/light conflicts, action
   feasibility, dialogue ownership, and unwanted music/subtitles.

## Generation and workbench

Save each raw output unchanged and its record at
`05_shots/<shot-id>/takes/<take-id>/take.json`. Record exact prompt version, changed
section, input hashes, model/UI settings, remote job, media metadata, output hash, and
nonempty `coverage_requirement_ids` at review. Those IDs must be an exact subset of the
current shot requirements; inputs include the current `shot.json` path and hash.
Inspect beginning, middle, end, crop, audio stream, and first visible failure.

Change one structured section per diagnostic retry. If the source asset fails, return
to Asset lock. If the contract fails, return to Shot still. Simplify repeated complex
failure instead of adding prose indefinitely.

## Gate

Show the unedited raw clip before retiming, compositing, color, or audio replacement.
Use `scripts/prepare_review.py` with subject type `TAKE`, exact project/output hashes,
and `--apply`, then stop at the central `USER_REVIEW_REQUIRED` request. The output media
and hashed `take.json` evidence become immutable at that point; `record_decision.py`
changes only the central approval. A changed candidate requires a new `take_id`.
For a multi-shot project, RAW_VIDEO closes only when every board-defined coverage ID
reaches `minimum_approved_takes` using exact-output central `USER_APPROVED` TAKE decisions,
and every other take has a terminal central `REJECTED`, `SUPERSEDED`, or
`EXCLUDED_FROM_INPUTS` decision. Each
accepted take keeps its own central approval and immutable output hash. A shot or take
change invalidates source, edit, and delivery descendants through the reset matrix.
Source-library selection is not stored in `take.json`; membership in the centrally
approved `SOURCE_LOCKED` manifest is the only source-selection authority.
