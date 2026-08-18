# 01 — Pipeline, project records, and naming

Use file-backed records as authority. Chat memory may recall context but never selects
the current approved artifact.

## Contents

- [Canonical handoffs](#canonical-handoffs)
- [Start a project](#start-a-project)
- [Modes](#modes)
- [Record naming](#record-naming)
- [Status and exclusion](#status-and-exclusion)

## Canonical handoffs

```text
STORY → STORYBOARD → LOOKDEV → ASSETS → SHOT STILL
→ RAW VIDEO → SOURCE LIBRARY → EDIT → DELIVERY
```

Every handoff requires an artifact ID, current hash, provenance, and approval. Run the
workflow for the earliest missing gate and stop after producing one reviewable result.

## Start a project

Use `scripts/init_project.ps1` with an explicit absolute target. It creates the project
from `templates/` without overwriting existing files by default. Then run
`scripts/validate_project.py`.

Keep skill instructions outside the film project. A project contains only its own
records and artifacts:

```text
<project>/
├─ project.json
├─ 00_schemas/schema-manifest.json
├─ 01_story/
│  ├─ STORY_CONTRACT.md
│  └─ history/story-contract/vNNN/{STORY_CONTRACT.md,evidence/...}
├─ 02_storyboard/
│  ├─ storyboard.json
│  ├─ panels/<panel-id>.png
│  └─ history/<storyboard-id>/vNNN/{storyboard.json,evidence/...}
├─ 03_lookdev/
│  ├─ VISUAL_BIBLE.md
│  └─ history/visual-bible/vNNN/{VISUAL_BIBLE.md,evidence/...}
├─ 04_assets/
│  ├─ asset-index.json
│  └─ records/<asset-id>/asset.json
├─ 05_shots/<shot-id>/
│  ├─ shot.json
│  ├─ prompts/
│  ├─ stills/
│  ├─ history/vNNN/{shot.json,evidence/...}
│  ├─ takes/<take-id>/take.json
│  └─ review/
├─ 06_source_library/
│  ├─ source_manifest.json
│  └─ history/<library-id>/vNNN/{source_manifest.json,evidence/...}
├─ 07_edit/
│  ├─ timeline.json
│  └─ records/<timeline-id>/v###/timeline.json
├─ 08_delivery/
│  ├─ delivery.json
│  └─ records/<delivery-id>/v###/delivery.json
├─ 09_approvals/
└─ 99_logs/
```

Use project-relative paths in records. Store SHA-256 hashes so OneDrive, Korean text,
and moved project roots do not break artifact identity.

## Modes

- `GUIDED`: make decisions with the user and persist them to the same records.
- `JSON`: validate and execute existing decisions; stop on a missing material choice.
- `RAW_SOURCE_FIRST`: approve the source library before editing.
- `ASSEMBLY_WHILE_GENERATING`: assemble approved sources and request missing coverage.
- `CONCEPT_EXPLORATION`: explore quickly without silently promoting outputs.

## Record naming

Use stable IDs independent of filenames:

```text
project: take-me
scene: S01
shot: S01_SH020
asset: char_take-me_woman_seated_v03
take: S01_SH020_T03
coverage: COV_S01_SH020_MASTER
approval: APR_S01_SH020_T03_001
```

Keep exact remote Higgsfield tags separately:

```text
@char_take-me_woman_seated_v03
@loc_take-me_moon_terrace_night_v02
@prop_take-me_letter_open_v01
```

Never invent an `@` tag. A planned name is not a remote Element.

## Status and exclusion

Use schema-defined decision statuses in central approval records. Asset/take records
contain no lifecycle mirror; collection and source selection resolve central approvals
and source-manifest membership. A rejected or replaced file remains useful as evidence;
its central decision is `REJECTED`, `SUPERSEDED`, or
`EXCLUDED_FROM_INPUTS`, and downstream validators must refuse it.

Approvals bind to hashes. All nine production subject content records omit top-level
`review_status` and `approval_id`; if their bytes change, obtain a new central approval.
Do not copy an old `USER_APPROVED` decision onto a changed artifact.

All approval records live in `09_approvals/`; stage directories contain artifacts and
review evidence, never competing approval authorities. A picture-locked timeline and
a rendered delivery are separate immutable authorities.

Story, storyboard, lookdev, shot, and source library retain fixed current paths. Before review, copy the
exact authority to its next `history/<subject-id>/vNNN/` destination and mirror every
other file-backed evidence item below
`history/<subject-id>/vNNN/evidence/<original-project-relative-path>`. Approval evidence
must include equal-hash current/archive pairs. Follow
`references/12-invalidation-and-revisions.md` before replacing a fixed current file.
Shot snapshots use `05_shots/<shot-id>/history/vNNN/`; source snapshots use
`06_source_library/history/<library-id>/vNNN/`. Timeline and delivery instead preserve
each review candidate at its own record path from central `USER_REVIEW_REQUIRED` onward;
do not create redundant history snapshots for them. A rejected v001 remains in place
and the next candidate uses v002 with a terminal predecessor link.

Asset and Take approvals target immutable master/output media. Their `asset.json` and
`take.json` are mandatory hashed evidence and become immutable with that media when the
central approval enters `USER_REVIEW_REQUIRED`. A changed candidate gets a new
`asset_id` or `take_id`; never patch lifecycle or source-selection state into reviewed
evidence. Take source selection exists only in the approved `SOURCE_LOCKED` manifest.

`templates/TEMPLATE_MAP.json` declares this through `review_snapshot_root`,
`versioned_review_destination`, `versioned_review_evidence_destination`,
`snapshot_before_approval_status`, and `review_version_format`. Project initialization seeds only current starter files; the
stage workflow allocates and copies each review version when real bytes exist.
The Asset/Take entries separately declare `central_subject_type`, `subject_authority`,
`evidence_record_immutable_after_approval_status`, `first_review_only`, and the new-ID
replacement rule.

Close collection gates against the current approved project-wide storyboard: every
`asset_plan` item needs an approved asset, every `shot_plan` item needs an approved
shot, and every coverage minimum needs enough centrally approved takes. Resolve extra
candidate records with terminal central decisions; never hide them from folder scans.
