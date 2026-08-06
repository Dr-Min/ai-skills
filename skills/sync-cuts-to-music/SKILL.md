---
name: sync-cuts-to-music
description: Analyze local music for transient-dense fills and musical cut regions, review exact cut evidence, arrange supplied images or videos on those cuts, and export either a version-independent split-media package or an experimental editable CapCut JSON draft clone. Use when users ask to sync image or video changes to music, find rapid beat sections, visualize why cuts were chosen, build beat-cut previews, split timelines for CapCut, or generate a CapCut draft from local media.
---

# Sync Cuts to Music

Create cut timelines from actual transient attacks instead of imposing a uniform BPM grid. Keep analysis common and separate the two output modes:

- `split-package`: render numbered visual clips, continuous audio, timing CSV/JSON, diagnostic PNG, reference MP4, and manifest.
- `capcut-json`: first create the same split package, then clone a CapCut template draft and populate its JSON with those rendered clips and continuous audio. The clip timing and order remain editable; zoom and color are baked into v1 clips rather than exposed as native CapCut keyframes.

## Required opening questions

Before analysis, ask only the missing questions:

1. Resolve the input files. Use attached or explicitly named local music and visual files. If either side is missing, ask for the missing file or path.
2. Ask for the target duration or end point when the user has not already specified it. Default to the full track only when that is clearly intended.
3. Ask: `컷 전환에 효과를 넣을까요? 효과 없음 / 줌인만 / 색상 변화만 / 줌인+색상 변화`
   - If zoom is selected, ask: `약하게 3% / 보통 6% / 강하게 10%`.
   - Keep flash off unless explicitly requested.
4. Ask: `강조하고 싶은 구간의 대략적인 힌트를 주세요. 예: 4~6초, 9초 이후. 힌트가 없으면 전체를 탐색합니다.`
   - Treat hints as search guidance, never exact boundaries.
5. When multiple visual files exist, default to name order, round-robin placement, and continuous source progression. Ask only if the user wants another order.

Do not ask for output mode until the user has reviewed the diagnostic unless they already chose it.

## Workflow

1. Preserve source audio, video, images, and CapCut drafts. Write only versioned outputs or explicit clones.
2. Run `doctor` to resolve Python dependencies and FFmpeg before analysis.
3. Run `analyze` with the user's effects and approximate hints to create `cut_plan.json`.
4. Run `visualize` to create the spectrogram and exact rendered-frame markers.
5. Show the diagnostic and report:
   - detected and frame-rounded cut times;
   - transient confidence;
   - proposed active windows;
   - any release point without a nearby attack.
6. Wait for user approval before rendering the whole requested duration.
7. Run `render-package` with the approved plan and supplied media.
8. Ask for output: split package, CapCut JSON clone, or both.
9. For CapCut JSON, read `references/capcut-json.md`. If several compatible templates exist, list draft name, modification time, and observed schema/version, then ask which one to copy. Run `export-capcut-json` only against the copy. Never edit a live draft in place.
10. Run `verify` and report frame count, duration, media count, hashes, and what remains untested in CapCut itself.

## Commands

Use the same Python environment for all commands. Pass `--ffmpeg` when FFmpeg is not on `PATH`.

```powershell
python scripts/beat_cut.py doctor

python scripts/beat_cut.py analyze `
  --audio <music.wav> `
  --duration 15 `
  --hint 4:6 `
  --hint 9: `
  --zoom medium `
  --color cycle `
  --output <cut_plan.json>

python scripts/beat_cut.py visualize `
  --audio <music.wav> `
  --plan <cut_plan.json> `
  --output <cut_diagnostic.png>

python scripts/beat_cut.py render-package `
  --plan <cut_plan.json> `
  --audio <music.wav> `
  --media <A.mp4> <B.mp4> <C.mp4> `
  --diagnostic <cut_diagnostic.png> `
  --output-dir <package-dir>

python scripts/beat_cut.py export-capcut-json `
  --package-dir <package-dir> `
  --template-draft <copied-template-draft> `
  --output-draft <staged-draft>

python scripts/beat_cut.py verify --package-dir <package-dir>
```

## Analysis rules

- Use global BPM only as a reference and for sanity checks.
- Detect cut candidates from positive spectral flux over 180 Hz to 12 kHz plus short-term RMS attack.
- Convert detected times to the first legal rendered frame using `ceil(time * fps)`.
- In `fill-only` mode, favor increases in transient density over steady quarter-note repetition.
- End a hinted range on a real attack near the hint. End an open-ended dense run at the first actual attack after its separating gap.
- Default to holding the final visual after the active run; do not insert a silent reset cut.
- Warn about rapid flashing and keep white flash disabled by default.

Read `references/algorithm.md` when tuning thresholds or diagnosing missed/extra cuts. Read `references/output-contract.md` before changing plan or package schemas.

## CapCut JSON guardrails

- Treat CapCut JSON as experimental and version-specific.
- Create a rendered split package first; populate CapCut with those exact clips so the JSON timeline matches the approved reference.
- Require a template draft containing at least one local video segment and one local audio segment.
- Stage outside CapCut's live draft root by default.
- If installing into the live draft root, require CapCut to be fully closed and copy the template to a new sibling folder first.
- Preserve `draft_content.json.bak`, update both content and metadata paths, generate new IDs, and validate every segment material reference.
- Fall back to the split package when the schema or version is unsupported.

## Completion criteria

- `cut_plan.json` validates and records source hash, settings, detected times, rendered frames, and release evidence.
- Diagnostic PNG visibly distinguishes cuts, releases, candidates, and attack intensity.
- Package clips are non-empty, visual-only, name-sorted, and sum to the exact total frame count.
- Continuous audio matches the requested duration.
- Reference MP4 decodes through the full duration.
- CapCut staged draft JSON parses, all segment references resolve, and target ranges cover the timeline without overlaps or gaps.
- Never claim the CapCut project is fully verified until it opens and plays correctly in the installed CapCut version.
