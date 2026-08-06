# Cinematic Video Pipeline

[전체 스킬 목록](../../README.md) · [실행 지침](SKILL.md)

Turn a text prompt into a smooth, high-resolution cinematic video clip through four
stages:

```
image prompt ──▶ [1] 4K still ──▶ [2] image-to-video ──▶ [3] 60fps ──▶ [4] upscale
   (Higgsfield GPT Image 2)  (Higgsfield Seedance 2.0)  (RIFE, local)  (ESRGAN, local, optional)
```

Stages 1–2 call the Higgsfield API (credits). Stages 3–4 run on your local NVIDIA GPU
and are free. This repo is a [Claude Code / Agent Skill](https://docs.claude.com) —
drop it into `~/.claude/skills/` and Claude can drive the whole pipeline for you — but
`scripts/pipeline.py` is a plain CLI you can also run by hand.

## Install

From the monorepo root:

```bash
python install.py --no-law-mcp --skills cinematic-video-pipeline
```

## Quickstart

```bash
python skills/cinematic-video-pipeline/scripts/pipeline.py \
  --image-prompt "<the 4K still prompt>" \
  --motion-prompt "<the camera / subject motion prompt>" \
  --outdir ./out --name myshot --duration 5 --fps 60
```

Outputs are numbered in pipeline order:

```
myshot_01_reference_4k.png      the still
myshot_02_video_24fps.mp4       raw Higgsfield video
myshot_03_video_60fps.mp4       interpolated  ← usually the deliverable
myshot_04_video_60fps_up2x.mp4  upscaled (only with --upscale)
```

Already have a start image? Pass `--image PATH` to skip generation. Already have a raw
video? Pass `--video PATH` to run only the local 60fps + upscale stages (no credits).

Use `--stop-after image|video|interpolate` for cheap checkpoints, and test at
`--duration 5` before committing to `--duration 10`.

## Requirements

| Dependency | Purpose | Notes |
|---|---|---|
| **Higgsfield CLI**, authenticated | stages 1–2 (image + video) | `higgsfield account status` must succeed; needs your own account/credits |
| **NVIDIA GPU** | stages 3–4 (local) | tested on a 4070 Ti; 4K interpolation fits in 12 GB |
| **Waifu2x-Extension-GUI** | bundles the RIFE + Real-ESRGAN NCNN engines | set `W2X_DIR` to its folder if auto-detect misses it |
| **ffmpeg** on PATH, or `pip install imageio-ffmpeg` | frame extraction + encoding | the script falls back to the imageio bundle |

### Setup

1. Install and authenticate the Higgsfield CLI.
2. Install [Waifu2x-Extension-GUI](https://github.com/AaronFeng753/Waifu2x-Extension-GUI)
   (Windows). It ships the `rife-ncnn-vulkan` and `realesrgan-ncnn-vulkan` engines the
   script calls.
3. Point the script at it if needed:
   ```bash
   # Windows (PowerShell)
   setx W2X_DIR "C:\path\to\Waifu2x-Extension-GUI"
   # macOS/Linux
   export W2X_DIR="/path/to/Waifu2x-Extension-GUI"
   ```
4. `pip install imageio-ffmpeg` (or put `ffmpeg` on PATH).

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--image-prompt` / `--image` | — | one is required; `--image` skips generation |
| `--motion-prompt` | — | required; the camera/subject movement |
| `--video` | — | reuse an existing raw video, run only local stages |
| `--duration` | `5` | seconds; test at 5 before 10 |
| `--fps` | `60` | interpolation target |
| `--aspect` | `16:9` | e.g. `9:16` for reels |
| `--video-model` | `seedance_2_0` | 4K-native, holds background locked |
| `--video-res` | `4k` | `1080p` is much cheaper for drafts |
| `--rife-model` | `rife-v4.26` | under `Waifu2x-Extension-GUI/rife-ncnn-vulkan/` |
| `--upscale` | off | adds the Real-ESRGAN stage |
| `--upscale-model` | `realesr-animevideov3-x2` | anime-video model; temporally stable |
| `--stop-after` | — | `image` \| `video` \| `interpolate` for cheap checkpoints |

## Prompt design

`references/prompt-design.md` documents one proven shot type (the slow parallax arc).
It is a recipe, not a rule — write prompts from the concept you actually want.

## Notes on encoding

Every output is 8-bit H.264 High `yuv420p` so stock players (including Windows') open
it. Audio is re-muxed from the source video because RIFE/ESRGAN operate on silent
frames.

## License

MIT — see [LICENSE](LICENSE).
