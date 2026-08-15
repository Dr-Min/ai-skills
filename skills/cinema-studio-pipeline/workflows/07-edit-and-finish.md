# 07 — Edit, finish, and delivery

Assemble approved source ranges without changing their master files.

## Edit

Create `timeline.json` from approved source IDs and ranges. Give every cut a story,
gaze, action, spatial, emotional, or music-event reason. Use
`integrations/sync-cuts-to-music.md` only to propose events; do not retime raw sources
or replace story cuts automatically.

Export a deterministic edit plan with `scripts/export_timeline.py`. Store proxies,
previews, retimes, effects, and audio mixes as derived files with parents and hashes.
Complete the exact review-candidate edit and set content `lock_status: PICTURE_LOCKED`
before hashing it. Lock alone is not approval. Create a central TIMELINE approval whose
`subject_sha256` targets that exact record and whose evidence also binds the current
source-manifest path/hash; set the approval to `USER_REVIEW_REQUIRED`, show the edit,
and stop. From that moment the timeline path is immutable. A user decision changes only
the central approval to `USER_APPROVED` or `REJECTED`.

Version one may use `07_edit/timeline.json`. After either approval or rejection, the next
candidate uses `07_edit/records/<timeline-id>/v###/timeline.json`; fill
`supersedes_timeline` with predecessor ID/version/path/SHA/approval and advance
`project.authority_files.timeline`. The predecessor approval must be terminal
`USER_APPROVED` or `REJECTED`; preserve that decision and connect reciprocal replacement
links. The successor gets its own central approval and exact hash. Do not create a
fixed-path history copy: each timeline record path is already immutable and unique.

## Finish in order

1. picture assembly and timing;
2. picture lock;
3. local cleanup from immutable sources;
4. neighboring-shot color unification;
5. dialogue cleanup, continuous ambience, effects, and music;
6. delivery render and full QA.

Do not grade before a broken face/hand/edge is repaired. Do not feed a full-frame
edited derivative back into an image model. Generate a fresh patch from the immutable
source and composite only its approved region.

## Delivery authority

Create a new immutable `delivery.json` version for each review render. Bind it to the exact
locked timeline ID, path, and SHA-256; the master path and SHA-256; derivation tool,
settings, and input hashes; and evidence-bearing QA. Never overwrite a record after its
central approval reaches `USER_REVIEW_REQUIRED`. Version one may use `08_delivery/delivery.json`;
later versions use `08_delivery/records/<delivery-id>/v###/delivery.json`, fill
`supersedes_delivery`, and advance `project.authority_files.delivery_record` while
preserving every predecessor. Link approvals reciprocally; a predecessor keeps its
terminal `USER_APPROVED` or `REJECTED` decision because its exact authority remains immutable. Do not copy
timeline or delivery into fixed-current history trees.

Require evidence-bearing `media_integrity.status: PASS`. Verify resolution, frame rate,
color space, duration, crop, and exactly one `FIRST_FRAME`, `MIDDLE_FRAME`, and
`LAST_FRAME` evidence item with path/SHA/frame address. When `audio_present` is true,
record audio metadata and require audio-sync PASS; when false, keep metadata null and
use audio-sync `NOT_APPLICABLE` with a reason. Record rights evidence as applicable.

The central `09_approvals/<approval-id>.json` FINISH approval targets the current
`delivery.json` hash and includes the rendered master and QA artifacts as evidence.
Set it to `USER_REVIEW_REQUIRED`, show those exact bytes, and stop; the decision changes
only that central record, never the delivery content.
Finish is valid only while its source timeline is
still the same approved `PICTURE_LOCKED` file. Superseding EDIT invalidates delivery
and FINISH; a new render receives a new delivery record and central approval. Follow
the complete reset matrix in `references/12-invalidation-and-revisions.md`.
