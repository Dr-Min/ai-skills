# 12 — Invalidation and immutable revisions

An ID names a production concept. An approval ID plus SHA-256 selects one exact
version. Reusing an ID never carries approval across changed bytes.

## Contents

- [Reset protocol](#reset-protocol)
- [Gate reset matrix](#gate-reset-matrix)
- [Record and pixel invalidation matrix](#record-and-pixel-invalidation-matrix)
- [Dependency chain](#dependency-chain)
- [Asset and take evidence immutability](#asset-and-take-evidence-immutability)
- [Fixed-authority review snapshots](#fixed-authority-review-snapshots)
- [Immutable timeline revisions](#immutable-timeline-revisions)
- [Immutable delivery revisions](#immutable-delivery-revisions)

## Reset protocol

When an authority changes, preserve its old versioned file or fixed-authority review
snapshot and its central approval in `09_approvals/`. Content authorities carry no
top-level approval state. Mark the affected gate `SUPERSEDED`, reset every dependent later gate
to `DRAFT`, remove stale IDs from `project.active_approval_ids`, and set
`current_stage` to the earliest invalid gate. Restart deliberately with the guarded
`SUPERSEDED -> DRAFT` transition; never delete rejection or replacement evidence.

## Gate reset matrix

| Superseded gate | Also invalidates |
| --- | --- |
| STORY | STORYBOARD, LOOKDEV, ASSET_LOCK, SHOT_STILL, RAW_VIDEO, SOURCE_LIBRARY, EDIT, FINISH |
| STORYBOARD | LOOKDEV, ASSET_LOCK, SHOT_STILL, RAW_VIDEO, SOURCE_LIBRARY, EDIT, FINISH |
| LOOKDEV | ASSET_LOCK, SHOT_STILL, RAW_VIDEO, SOURCE_LIBRARY, EDIT, FINISH |
| ASSET_LOCK | SHOT_STILL, RAW_VIDEO, SOURCE_LIBRARY, EDIT, FINISH |
| SHOT_STILL | RAW_VIDEO, SOURCE_LIBRARY, EDIT, FINISH |
| RAW_VIDEO | SOURCE_LIBRARY, EDIT, FINISH |
| SOURCE_LIBRARY | EDIT, FINISH |
| EDIT | current delivery record, rendered master, QA evidence, and FINISH |
| FINISH | no earlier gate; create another immutable delivery revision for a rerender |

## Record and pixel invalidation matrix

| Changed authority or bytes | Invalidate or recalculate |
| --- | --- |
| `STORY_CONTRACT.md` | story approval and every later gate |
| `storyboard.story_dependency` | storyboard approval and every gate after STORY |
| `asset_plan`, `scenes`, nested panel data, panel image bytes/hash, or `shot_plan`/coverage | storyboard approval, LOOKDEV, and every later gate |
| `VISUAL_BIBLE.md` | look approval, all asset approvals, and every dependent shot/take/source/edit/delivery |
| planned asset added/removed/renamed | board approval, ASSET_LOCK collection closure, and all later gates |
| reviewed `asset.json`, source image, descriptor, state, or verified remote identity | do not mutate it; create a new asset ID/approval, then invalidate dependent shots, takes, and descendants |
| `shot.json`, `dependency_snapshot`, coverage/panel IDs, still, or boundary-frame bytes | that shot approval, its takes, source library, edit, and delivery descendants |
| reviewed `take.json`, output media, prompt/settings, input hash, or coverage IDs | do not mutate it; create a new take ID/approval, then recalculate coverage, source library, edit, and delivery |
| source membership, handle, source path, or hash in `source_manifest.json` | source-library approval, EDIT, and FINISH |
| timeline clips/events/source hashes or record bytes | EDIT approval, every delivery derived from it, and FINISH |
| delivery record, master bytes, derivation settings, or QA artifact | current FINISH approval only; preserve earlier delivery versions |
| rights, consent, license, or required-credit evidence | every approval whose permitted use depended on that evidence |

An unplanned or extra asset, shot, or take candidate cannot disappear silently. Before
its collection gate closes, give it its own current approval or a terminal
`REJECTED`, `SUPERSEDED`, or `EXCLUDED_FROM_INPUTS` status. Coverage counts use only
current centrally approved immutable takes.

## Dependency chain

- `storyboard.story_dependency` binds the current approved story path and hash.
- Storyboard approval evidence binds `storyboard.json` and every panel
  `image_file`/`image_sha256`.
- Every review-ready shot snapshots current story, storyboard, lookdev, and every
  required asset approval ID, subject hash, authority path, and approval-record path.
- Every review-ready take records nonempty `coverage_requirement_ids` and binds the
  current `shot.json` through `input_hashes`.
- The source manifest binds centrally approved take IDs, files, hashes, and handles;
  `SOURCE_APPROVED` exists only on admitted manifest items.
- The timeline binds approved source paths/hashes and declares `PICTURE_LOCKED` before
  review; the delivery binds one exact timeline path/hash with a central EDIT approval.

```text
story -> project-wide board + panel pixels -> look -> approved assets
  -> shot.json + still pixels -> take output -> source manifest
  -> picture-locked timeline -> delivery record + master + QA
```

If an arrow no longer resolves to the same current path and SHA-256, validation fails
even when the human-readable ID did not change.

## Asset and take evidence immutability

ASSET and TAKE approvals target immutable media bytes, not their JSON records. The
review package nevertheless includes the current `asset.json` or `take.json` path/hash
as mandatory evidence. Therefore both the media subject and JSON evidence record become
immutable when the central approval enters `USER_REVIEW_REQUIRED`.

Run `scripts/prepare_review.py` only for a subject's first current review and supply
exact project/subject SHA values. It fails closed with `E_REVISION_WORKFLOW_UNSUPPORTED`
when a current review, approval, or rejection already owns that subject ID. Record the
user decision with `scripts/record_decision.py` and its exact project/approval/subject
CAS hashes. Neither command writes lifecycle state into the content record.

Terminal decisions also require a machine-local authenticated receipt stored outside
the project. The receipt binds the canonical project root and exact decision package.
Moving or importing a project invalidates that binding; obtain a new approval or use an
explicit receipt-migration workflow. Never copy or hand-edit receipt or key files.

After review request, never update notes, provider metadata, diagnosis, coverage,
remote evidence, or source-selection fields in place. Produce a new `asset_id` or
`take_id`, preserve old media/record/central decision, and rerun collection closure.
Take membership is represented solely by an item in a centrally approved
`SOURCE_LOCKED` source manifest; exclusion is a terminal central TAKE decision.

## Fixed-authority review snapshots

Five content authorities retain fixed current paths. Before the central approval for any
of them enters `USER_REVIEW_REQUIRED`, allocate the next unused zero-padded `vNNN` and
make byte-identical immutable copies:

| Subject | Authority snapshot |
| --- | --- |
| `story-contract` | `01_story/history/story-contract/vNNN/STORY_CONTRACT.md` |
| `<storyboard-id>` | `02_storyboard/history/<storyboard-id>/vNNN/storyboard.json` |
| `visual-bible` | `03_lookdev/history/visual-bible/vNNN/VISUAL_BIBLE.md` |
| `<shot-id>` | `05_shots/<shot-id>/history/vNNN/shot.json` |
| `<library-id>` | `06_source_library/history/<library-id>/vNNN/source_manifest.json` |

For every other file-backed visual, source, or prerequisite evidence item, copy the bytes to
`<snapshot-root>/vNNN/evidence/<original-project-relative-path>`. Thus a storyboard
snapshot preserves every current panel image, a shot snapshot preserves every still,
and a source snapshot preserves every admitted source. Never reuse a version, mutate an archive file, or use
an archive as the current authority.

Hash both sides after copying. The central pending/current approval evidence contains one item
for the current authority path and one for its authority snapshot with the same SHA-256,
plus a current/archive pair for every supporting file. `subject_sha256` equals both
authority hashes. Before a fixed current path is replaced, every distinct non-null SHA
in the old approval evidence must still match at least one actual file below that
subject's `history/` root; otherwise stop without replacing the authority.

For a fixed-path revision, first create the successor approval as `DRAFT` with
`supersedes_approval_id` set. After archive verification, an old `USER_APPROVED`
decision alone changes to `SUPERSEDED`; set `superseded_by_approval_id` and keep its
subject, hashes, evidence, actor, decision time, and earlier predecessor link unchanged.
An old `REJECTED` decision stays `REJECTED`, receives only the reciprocal successor link,
and keeps its rejected bytes in history. Remove stale active IDs, reset dependent gates,
then replace the current authority, create successor snapshot/evidence pairs, and request
review. Legacy targets/evidence arrays must not be rewritten.

## Immutable timeline revisions

- Timeline v001 may live at `07_edit/timeline.json` with
  `supersedes_timeline: null`.
- Set content `PICTURE_LOCKED` before central review. It is not approval by itself.
- From central `USER_REVIEW_REQUIRED` onward, that record path is immutable, whether the
  final decision is `USER_APPROVED` or `REJECTED`.
- A later edit lives at
  `07_edit/records/<timeline-id>/v###/timeline.json`. Its `supersedes_timeline` binds
  predecessor ID, version, path, SHA-256, and approval ID.
- Preserve the predecessor, advance `project.authority_files.timeline`, then obtain a
  new EDIT approval. The predecessor approval remains terminal `USER_APPROVED` or
  `REJECTED`; set its `superseded_by_approval_id` and the successor's reciprocal
  `supersedes_approval_id`. A pointer advance alone is not approval.

## Immutable delivery revisions

- Delivery v001 may live at `08_delivery/delivery.json` with
  `supersedes_delivery: null`.
- From central `USER_REVIEW_REQUIRED` onward, a delivery record path is immutable. A rerender or replacement after approval or rejection lives at
  `08_delivery/records/<delivery-id>/v###/delivery.json`. Its predecessor binding,
  locked-timeline binding, master hash, derivation inputs, and QA must all be current.
- Review-ready and approved delivery requires evidence-bearing
  `media_integrity.status: PASS`, exactly one FIRST/MIDDLE/LAST frame role, and the
  schema-defined audio-present/audio-sync branch.
- Preserve every terminal predecessor, advance
  `project.authority_files.delivery_record`, then obtain a new FINISH approval. The
  predecessor approval stays `USER_APPROVED` or `REJECTED`; link it reciprocally to the successor.

Timeline and delivery need no fixed-path review-history copy because every exact reviewed
authority remains at its own record path. Never overwrite or move
that predecessor, and never edit an old approval to pretend it targets new bytes.
