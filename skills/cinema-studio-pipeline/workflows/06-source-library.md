# 06 — Immutable source library

Build the authoritative edit inputs from approved raw takes.

## Admission rules

- Admit only a take whose exact output path/hash has a current central
  `USER_APPROVED` TAKE decision.
- Preserve the original filename or source ID, media metadata, prompt version, input
  hashes, provider job, and approval.
- Record usable in/out handles without trimming or rewriting the master file.
- Exclude rejected, superseded, and derived previews.
- Verify hashes and parent relationships with `scripts/verify_lineage.py`.

In `RAW_SOURCE_FIRST`, do not begin creative editing until all required coverage or an
explicitly approved reduced source plan is present. A reduced plan is a new approved
storyboard/coverage revision, not a note that bypasses requirements. In
`ASSEMBLY_WHILE_GENERATING`, add only approved sources and add missing coverage by
revising the authoritative shot plan before generating it.

Never accelerate, slow, stabilize, upscale, recolor, or remix a raw master in place.
Every transformed file is a child with its own lineage.

`SOURCE_APPROVED` exists only on each admitted `source_manifest.json.sources[]` item.
Absence from the manifest means not selected; never mutate a reviewed `take.json` to
record library membership.

## Output and gate

Write `source_manifest.json` under `06_source_library/` and validate it. Complete its
membership and set `lock_status: SOURCE_LOCKED` before review; lock alone is not approval.
Copy identical bytes to
`06_source_library/history/<library-id>/vNNN/source_manifest.json` and mirror every
file-backed source/evidence item under that version's
`evidence/<project-relative-path>`. Bind current/archive pairs and the manifest hash in
the central source-library approval, set that approval to `USER_REVIEW_REQUIRED`, show
the exact sources, and stop. The manifest has no top-level approval state and is never
rewritten after hashing for review. Advance only when its exact current hash has a
central `USER_APPROVED` decision and the sources satisfy the board coverage plan.
On replacement, old approved decisions become `SUPERSEDED`; rejected decisions remain
`REJECTED`, and both keep their history bytes. A manifest revision invalidates EDIT and FINISH.
