---
name: cinema-studio-pipeline
description: >-
  Operate a stateful Higgsfield Cinema Studio and Seedance filmmaking pipeline from
  story contract through timed storyboard, mise-en-scene, locked assets, shot stills,
  raw video sources, edit, and delivery. Use for cinematic image or video production;
  Higgsfield project setup; character, wardrobe, location, prop, or mechanical-state
  continuity; Soul, AI Cast, Nano Banana, Seedream, or GPT Image routing; Seedance
  prompt writing and repair; JSON-driven shot execution; approval gates; immutable
  source lineage; music-synchronized cuts; dialogue, acting, QA, and finishing. Trigger
  for single shots and multi-scene films. Apply the project records and gates instead
  of improvising or advancing past unapproved work.
---

# Cinema Studio Pipeline v2

Run filmmaking as a file-backed production state machine. Treat prompts, model names,
and successful jobs as promises; treat approved pixels, sound, hashes, and visible
remote state as proof.

## Operating contract

1. Locate `project.json`. If it does not exist and the user asks to start production,
   run `scripts/init_project.ps1` with an explicit project root outside the skill directory.
2. Run `scripts/validate_project.py` before generation, after every record change, and
   before delivery.
3. Read `execution_mode`, `production_mode`, and the stage gates from `project.json`.
4. Find the earliest required gate without a valid approval. Load only its workflow
   and directly relevant references.
5. Produce one reviewable artifact. Story/Board/Look/Shot/Source fixed paths first copy
   exact authority/evidence bytes to their mapped immutable `history/.../vNNN/` paths.
   Then set the central approval to `USER_REVIEW_REQUIRED`, show those exact bytes, and stop.
6. All nine production subjects keep decision state only in `09_approvals/<approval-id>.json`;
   their content records contain no `review_status` or `approval_id`. Asset/take records become
   immutable evidence at review request; changed candidates require a new ID, and terminal decisions require an authenticated machine-local receipt.
7. Exclude `REJECTED`, `SUPERSEDED`, and `EXCLUDED_FROM_INPUTS` records from every
   downstream input lookup.

Do not claim a Higgsfield project, folder, Element, generation, or setting exists until
the authenticated service state is visible and recorded.
## Modes

### Execution mode

- `GUIDED` — interview, propose, show the artifact, and write the approved decisions
  into the same JSON records used by automation.
- `JSON` — execute pre-authored records only after schema, gate, reference, and lineage
  validation. Do not invent missing creative decisions silently.

### Production mode

- `RAW_SOURCE_FIRST` — finish and approve the immutable source library before editing.
  Default to this mode unless the project says otherwise.
- `ASSEMBLY_WHILE_GENERATING` — place approved sources into an assembly while producing
  and let the edit request missing coverage.
- `CONCEPT_EXPLORATION` — prioritize fast look discovery; never promote exploration
  outputs to production without a normal approval and lineage record.

### Shot generation mode

Select one mode per shot and read its workflow:

- `REFERENCE_TEXT_NATIVE` — `workflows/generation-modes/reference-text-native.md`
- `BOUNDARY_FRAME` — `workflows/generation-modes/boundary-frame.md`
- `MOTION_REFERENCE` — `workflows/generation-modes/motion-reference.md`
- `MUSIC_LIPSYNC` — `workflows/generation-modes/music-lipsync.md`

## Required gate order

| Gate | Workflow | Required evidence |
| --- | --- | --- |
| Story | `workflows/01-story.md` | approved story contract |
| Storyboard and look | `workflows/02-storyboard-and-lookdev.md` | approved project-wide board, hashed panel images, and visual bible |
| Asset lock | `workflows/03-asset-lock.md` | every planned asset resolved by a central exact-media approval |
| Shot still | `workflows/04-shot-still.md` | every planned shot approved with dependency snapshot and pixel evidence |
| Raw video | `workflows/05-raw-video.md` | approved immutable takes meeting every coverage minimum |
| Source library | `workflows/06-source-library.md` | source manifest with hashes and usable handles |
| Edit and finish | `workflows/07-edit-and-finish.md` | approved picture lock plus separate immutable delivery record and QA |

Inspection or repair may begin at the failing gate, but fix the earliest broken
handoff. Do not hide a bad asset with prompt bloat, a broken shot with speed changes,
or an unapproved source with downstream polish.

## Authority records

- `project.json` — modes, stage state, authoritative paths, provider project identity.
- `storyboard.json` — immutable reviewed content: `story_dependency`, asset/scene/panel pixels, shots, and coverage.
- `asset.json` — one immutable candidate's identity, role, state, descriptor, source hash, lineage, and verified remote identity.
- `shot.json` — purpose, camera/action contract, exact coverage IDs, dependency snapshot, active references, and hash-bound still evidence.
- `take.json` — one immutable take's coverage IDs, model/UI settings, prompt, input hashes, remote job, output metadata, diagnosis, and verdict.
- `approval.json` — one central `09_approvals/` decision binding target type, ID, exact hash, actor, evidence, time, and replacement.
- `timeline.json` — source ranges/events; set `PICTURE_LOCKED` before review. Central approval makes it effective; the path is immutable from review request onward.
- `delivery.json` — one immutable reviewed render authority: timeline hash, master, derivation, QA, and `media_integrity: PASS`.

Schemas are the machine contract; templates are starters. Records outrank chat memory.

Locks are content assertions; only a central exact-path/hash approval is a decision.

Collection gates close against the approved storyboard inventory and central decisions:
resolve every planned asset/shot, every coverage minimum, and every extra candidate.

## Reference role contract

Assign one schema-defined role to every `active_assets` input: `IDENTITY`, `WARDROBE`,
`STATE`, `LOCATION_GEOMETRY`, `MATERIAL_LIGHT`, `PROP_FUNCTION`, `MOTION`, `AUDIO`,
or `STYLE`. Record blocking panels in `storyboard_panel_ids` and start/end inputs in
`boundary_frames`; do not duplicate those structural roles in `active_assets`.

- Reject two active references that control the same property with conflicting states.
- Separate mutually exclusive states such as open/closed, dry/wet, intact/damaged,
  clean/bloodied, wardrobe A/B, and weapon retracted/extended.
- Treat every visible detail in a reference as activation pressure. Do not rely on a
  tiny label in a sheet to suppress an unwanted visible state.
- Use only actual uploaded references and saved `@` tags. Never invent an Element.
- Run `scripts/validate_references.py` before every image or video generation.

## Prompt and iteration contract

- Use a coherent one-paragraph decision order for image generation; read
  `references/02-prompting.md` plus the relevant location or character reference.
- Use the sealed structured shot document for Seedance; read
  `references/09-seedance-prompt-director.md` and acting rules when people perform.
- Separate Writer, Auditor, and Workbench: render a prompt from the shot record, audit
  stale tags and contradictions, then patch only the failed structured section.
- Change one diagnostic variable per iteration. Save the exact change and verdict.
- Simplify the shot after repeated controlled failure; do not endlessly enlarge prose.
- Preserve immutable originals. Generate a fresh patch from the original and composite
  only the changed region; never feed an edited derivative back as the new master.

## Conditional references and integrations

| Need | Read or run |
| --- | --- |
| Project setup and naming | `references/01-pipeline-and-setup.md` |
| Story, visual logic, and mise-en-scene | `references/story-and-mise-en-scene.md` |
| Image prompt construction | `references/02-prompting.md` |
| Model selection and pixel proof | `references/03-models-and-proof.md` and `providers/higgsfield/capabilities.yaml` |
| Location geography | `references/04-locations.md` |
| Character identity and state | `references/05-characters.md` |
| Motion/slop diagnosis | `references/06-seedance-and-slop.md` |
| Long-form production | `references/08-feature-production-system.md` |
| Seedance direction | `references/09-seedance-prompt-director.md` |
| Acting, dialogue, voice | `references/10-acting-and-dialogue.md` |
| Post and delivery | `references/11-post-production.md` |
| Invalidation and immutable revisions | `references/12-invalidation-and-revisions.md` |
| Likeness, voice, music, brand, and source rights | `references/rights-and-provenance.md` |
| Timed rough boards and optional spatial-control maps | `integrations/timed-storyboard.md` |
| Music transient cut proposals | `integrations/sync-cuts-to-music.md` |
| Higgsfield images and Elements | `providers/higgsfield/image-model-routing.md` and `providers/higgsfield/element-contract.md` |
| Higgsfield video and remote proof | `providers/higgsfield/seedance-routing.md` and `providers/higgsfield/remote-verification.md` |

`references/07-capstone.md` and `references/course-archive.md` are educational and
non-operational. Never route production from them when a current workflow exists.

## Deterministic tools

- Initialize: `powershell -File scripts/init_project.ps1 -ProjectRoot <absolute-path> -ProjectId <slug> -ProjectPrefix <2-6-uppercase> -Title <title>`
- Validate records: `python scripts/validate_project.py <project-root>`
- Validate active inputs: `python scripts/validate_references.py <project-root> --shot <shot.json>`
- Verify ancestry and hashes: `python scripts/verify_lineage.py <project-root>`
- Prepare first review: `python scripts/prepare_review.py <project-root> <SUBJECT_TYPE> <subject-id> --requested-by <actor> --expected-project-sha256 <sha256> --expected-subject-sha256 <sha256> --apply`
- Record user decision: `python scripts/record_decision.py <project-root> <approval-id> <approve|reject> --actor <actor> --expected-project-sha256 <sha256> --expected-approval-sha256 <sha256> --expected-subject-sha256 <sha256> [--reference <required-for-approve>] [--notes <required-for-reject>] --apply`
- Evaluate a gate transition: `python scripts/transition_status.py <project-root> <gate> <status>`
- Inspect media: `python scripts/inspect_media.py <media-file>`
- Extract review frames: `python scripts/extract_review_frames.py <video> <output-dir>`
- Build contact sheet: `python scripts/make_contact_sheet.py <frames-dir> --output <image>`
- Export an edit plan: `python scripts/export_timeline.py <timeline.json> <output-file>`
- Validate canonical and compatibility installs: `python scripts/validate_install.py`

The review CLIs use exact-hash CAS and support only a subject's first current review;
on `E_REVISION_WORKFLOW_UNSUPPORTED`, stop and use the explicit revision workflow.
## Non-negotiables

- Obtain user approval after storyboard/look artifacts and again after raw videos.
- Show raw generation results before editing them.
- Preserve exact source hashes and parent relationships.
- Keep storyboard logic separate from music analysis. Music events are edit proposals,
  not permission to retime raw sources or replace story-motivated cuts.
- For Seedance multimodal reference generation, prefer supplying the approved rough
  storyboard as an optional shot-structure/blocking reference when it materially clarifies
  action, geography, within-shot beat order, or camera language. The board never changes
  the shot's selected generation mode. `BOUNDARY_FRAME` pairs it with exact approved
  `START`/`END`; `REFERENCE_TEXT_NATIVE` uses role-specific assets without requiring a
  boundary frame; motion/audio modes retain their own required inputs. Never bind an
  annotated board as `START`, `END`, `IDENTITY`, `WARDROBE`, `STATE`, `LOCATION_GEOMETRY`,
  `MATERIAL_LIGHT`, or `PROP_FUNCTION`. A clean separately approved derivative may serve
  as `STYLE` only. Count every uploaded image against one provider budget, prioritizing
  mode-required boundaries and identity/state/location inputs over the optional board.
  Explicitly exclude panel borders, arrows, labels, graphite marks, and rough-board
  rendering from generated pixels.
- Record UI-controlled settings outside the prompt so the shot remains reproducible.
- Verify `media_integrity: PASS`, final crop, FIRST/MIDDLE/LAST frames, audio presence/sync, rights, and delivery bytes.
