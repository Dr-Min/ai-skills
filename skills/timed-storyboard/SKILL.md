---
name: timed-storyboard
description: Turn a story, treatment, script, or rough scene idea into a time-coded cinematic storyboard with shot-by-shot blocking, action phases, actor and prop movement paths, gaze direction, camera paths, continuity rules, storyboard images at four selectable roughness levels, and JSON/CSV/README exports. Use when planning visual narrative timing, mapping how actions change within a shot, drawing arrows and ghost positions, preparing rough boards or concept stills, or handing a storyboard to an AI video workflow. This skill is independent of music, beat detection, CapCut, and automatic rhythm editing.
---

# Timed Storyboard

Design the story first, then make every visible action, path, and camera change traceable over time. Treat seconds as narrative timing, never as music analysis.

## Keep the boundary clear

- Do not inspect audio, detect beats, or infer cuts from music.
- Do not invoke `sync-cuts-to-music`, CapCut JSON, zoom, color cycling, or flash logic unless the user explicitly requests a separate workflow.
- Accept approximate ranges such as `0~4초` as narrative hints. Preserve them as `hint_*` fields and propose exact shot timing separately.

## Ask only what is missing

1. Ask for the story, treatment, script, or scene idea.
2. Ask for the target duration when it is missing. Ask for aspect ratio and FPS only when delivery depends on them; otherwise default to 16:9 and 24 fps.
3. Show `assets/storyboard-levels-1-4.png` and ask for the default fidelity:
   - Level 1: thumbnail rough
   - Level 2: initial rough storyboard; default
   - Level 3: detailed production storyboard
   - Level 4: clean concept still plus a separate annotated motion card
4. Ask for rough scene ranges, required moments, prohibited elements, character references, and continuity constraints only when missing.
5. Ask whether timing should be user-locked or AI-proposed. Default to AI-proposed timing with an approval gate.

Read `references/roughness-levels.md` before generating storyboard images. Read `references/motion-notation.md` before designing blocking or annotations. Read `references/output-contract.md` before creating a project package or JSON.

## Workflow

### 1. Lock the story contract

State the cause, goal, stakes, obstacle, discovery, and choice in plain language. Identify the visible change each scene must communicate. Do not use a decorative cut as a substitute for a story event.

### 2. Build the timed sequence

Divide the total duration into scenes, shots, and action phases. Store integer frames as the timing source of truth and display seconds to three decimals.

For every shot, write:

- narrative purpose and visible change;
- start and end frames;
- opening image, action development, and closing image;
- transition in and out;
- continuity carried from the prior shot.

Use `hold -> anticipation -> action -> settle` when the action changes over time. Omit phases that are not visible instead of inventing filler.

### 3. Block every moving element

For every character, prop, camera, and important environmental element, specify:

- start, intermediate, and end state;
- screen position as normalized `x, y` coordinates from 0 to 1;
- path waypoints and the frame at which each is reached;
- body orientation, head direction, gaze target, and screen direction;
- entry, exit, stop, contact, occlusion, and handoff events;
- speed character such as still, hesitant, accelerating, steady, or abrupt.

Keep actor path, gaze path, prop path, and camera path separate. A static camera must be declared rather than left unspecified.

### 4. Produce an approval plan before images

Show the user:

1. timed shot list;
2. action-phase table;
3. blocking and path summary;
4. unresolved creative decisions.

Wait for approval when a proposed default changes story meaning, character behavior, geography, or duration.

### 5. Generate boards at the chosen level

- Keep panel aspect ratio equal to the target aspect ratio.
- Keep character positions, screen direction, moon/landmark position, and camera axis consistent unless a shot explicitly changes them.
- Add a compact legend once per page.
- Use ghost silhouettes and arrows for motion. Do not rely on prose alone when a path can be drawn.
- For Level 4, preserve a clean concept still and create a separate annotated motion card; never draw production arrows over the only clean reference.
- Generate start/middle/end panels when one panel cannot communicate the action unambiguously.

### 6. Review visual evidence

Inspect the actual output at its intended crop. Verify that the arrows, ghost positions, screen direction, contacts, entries/exits, and camera move are visually readable. Revise one decision at a time.

### 7. Export and validate

Use `scripts/storyboard_plan.py`:

```powershell
python scripts/storyboard_plan.py init --output <project-dir> --title <title> --duration 15 --fps 24 --level 2
python scripts/storyboard_plan.py validate --plan <project-dir>/storyboard_plan.json
python scripts/storyboard_plan.py export --plan <project-dir>/storyboard_plan.json --output <project-dir>
```

The exported project README must embed the four-level comparison image. Treat `storyboard_plan.json` as the machine-readable source of truth. Use `timing_summary.md`, `shotlist.csv`, `action_timeline.csv`, and `motion_paths.csv` as human-editable views.

## Completion criteria

- Every shot has a visible narrative change or a declared intentional hold.
- Shot timings fit the total duration without overlaps.
- Every changing action has ordered phases and a readable start/end state.
- Every moving subject and camera has a path or an explicit stationary declaration.
- Gaze, prop, and camera motion are not conflated with actor travel.
- Entry, exit, contact, occlusion, and screen-direction continuity are resolved.
- Storyboard images match the selected roughness level.
- JSON validates and README, detailed timing summary, shot list, action timeline, motion-path table, and image assets are present.
