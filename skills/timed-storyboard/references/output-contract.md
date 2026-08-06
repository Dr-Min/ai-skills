# Output contract

## Project package

```text
<project>/
  README.md
  timing_summary.md
  storyboard_plan.json
  shotlist.csv
  action_timeline.csv
  motion_paths.csv
  assets/
    storyboard-levels-1-4.png
  boards/
    contact-sheet.png
    annotated/
      S001.png
    clean/
      S001.png
  prompts/
    S001.txt
  references/
  exports/
```

Create only folders that receive files. Preserve versioned outputs; do not overwrite an approved board.

## Source-of-truth rules

- Treat `storyboard_plan.json` as authoritative for timing and blocking.
- Treat `timing_summary.md`, `shotlist.csv`, `action_timeline.csv`, `motion_paths.csv`, and `README.md` as derived human views.
- Store frames, not floating-point seconds, as exact timing.
- Use inclusive `start_frame` and exclusive `end_frame`.
- Give every scene, shot, character, prop, and reference a stable ID.
- Preserve user time hints separately from proposed timing.

## Required project fields

```json
{
  "schema_version": "1.0",
  "project": {
    "title": "Moon Promise",
    "duration_seconds": 15.0,
    "fps": 24,
    "aspect_ratio": "16:9",
    "default_roughness_level": 2,
    "timing_mode": "ai_proposed_user_approved"
  },
  "story_contract": {
    "cause": "",
    "goal": "",
    "stakes": "",
    "obstacle": "",
    "discovery": "",
    "choice": ""
  },
  "continuity": {
    "characters": {},
    "locations": {},
    "props": {},
    "screen_direction": ""
  },
  "scenes": [],
  "shots": []
}
```

## Required shot fields

```json
{
  "id": "S001",
  "scene_id": "SC01",
  "title": "Woman raises her head",
  "hint_start_seconds": 0.0,
  "hint_end_seconds": 4.0,
  "start_frame": 0,
  "end_frame": 96,
  "story": {
    "purpose": "Establish grief and the remembered promise",
    "visible_change": "Her gaze moves from the ground to the moon",
    "emotion_start": "withdrawn",
    "emotion_end": "alert but restrained"
  },
  "visual": {
    "shot_size": "close_up",
    "angle": "eye_level",
    "lens": "85mm feel",
    "composition": "face left third, moonlight from frame right",
    "axis": "woman faces screen right",
    "lighting": "soft blue-silver moonlight"
  },
  "characters": [],
  "props": [],
  "camera": {
    "mode": "static",
    "stationary": true,
    "start_framing": "close-up",
    "end_framing": "close-up",
    "target": "woman",
    "path": []
  },
  "environment_motion": [],
  "transition_in": "none",
  "transition_out": "cut",
  "continuity": [],
  "constraints": [],
  "board": {
    "roughness_level": 2,
    "panel_count": 3,
    "annotation_mode": "inline",
    "status": "planned",
    "image": "boards/annotated/S001.png",
    "concept_image": "boards/concept/S001.png"
  }
}
```

## Board files

- Name shots in timeline order: `S001`, `S002`, and so on.
- Keep clean and annotated files separate when Level 4 is used.
- Put shot timing, action phases, and the legend outside the artwork area when possible.
- Record generation prompt and approved source lineage for any generated image.

## Approval states

Use only:

- `planned`
- `timing_approved`
- `rough_generated`
- `rough_approved`
- `detailed_generated`
- `approved`
- `rejected`

Do not advance a shot to `approved` from a prompt alone. Inspect the generated pixels and intended crop.
