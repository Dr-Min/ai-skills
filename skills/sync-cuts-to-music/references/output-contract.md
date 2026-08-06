# Output contracts

## cut_plan.json

Required top-level fields:

- `schema_version`
- `created_utc`
- `audio`
- `settings`
- `analysis`
- `windows`
- `timeline`
- `status`

Each cut records `time` (the detected time), `strength`, `confidence`, `render_frame`, and `render_time`.
Each window records its hint, detected start, release attack, release frame, and evidence type.

## Split package

```text
package/
  01_video_clips/cut_001.mp4 ...
  02_audio/music_continuous.wav
  03_reference/reference.mp4
  04_timing/cut_timeline.csv
  04_timing/cut_plan.json
  04_timing/cut_diagnostic.png
  04_timing/package_manifest.json
  04_timing/concat_list.txt
```

Visual clips contain no audio. Place the single continuous WAV at timeline zero.

## package_manifest.json

Record:

- source paths and SHA-256 hashes;
- FFmpeg path and version when available;
- FPS, dimensions, duration, and total frames;
- ordered clip paths, frame counts, durations, and hashes;
- media placement policy and source offsets;
- verification results.

Never write secrets, account identifiers, or unrelated CapCut draft content.
