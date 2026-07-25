---
name: cinematic-video-pipeline
description: >-
  End-to-end pipeline that turns a text prompt into a smooth, high-res cinematic
  video clip: generate a 4K still (Higgsfield) -> image-to-video with a camera
  move (Higgsfield/Seedance) -> interpolate to 60fps locally (RIFE) -> optional
  local upscale (Real-ESRGAN). Use this whenever the user wants to make an AI
  video clip, an "arc"/orbit/parallax shot, a dreamy cinematic scene, a vertical
  or 16:9 reel, or asks to go from an image to a moving video, or to smooth /
  interpolate / upscale a generated clip. Trigger even if they only name part of
  the flow ("make this image move", "turn my prompt into a video", "boost this
  clip to 60fps"). Owns the mechanical pipeline; the user supplies the creative
  prompt.
---

# Cinematic Video Pipeline

Turn a concept into a finished cinematic clip through four stages. This skill owns
the **plumbing** — Higgsfield CLI calls, frame handling, interpolation, encoding.
You (with the user) own the **creative prompt**. Keep that split: the script never
invents a scene, and the pipeline mechanics never change per concept.

```
image prompt ──▶ [1] 4K still ──▶ [2] image-to-video (arc) ──▶ [3] 60fps ──▶ [4] upscale
   (Higgsfield GPT Image 2)   (Higgsfield Seedance 2.0)    (RIFE, local)   (ESRGAN, local, optional)
```

Stages 1–2 cost Higgsfield credits. Stages 3–4 run on the local GPU and are free.

## Quickstart

One command runs the whole thing. Run it with the Python that has `imageio_ffmpeg`
(or any Python if `ffmpeg` is on PATH):

```bash
python scripts/pipeline.py \
  --image-prompt "<the 4K still prompt>" \
  --motion-prompt "<the camera / subject motion prompt>" \
  --outdir "/c/Users/<you>/Downloads/<project>" \
  --name myshot --duration 5 --fps 60
```

Outputs land in `--outdir`, numbered in pipeline order:

```
myshot_01_reference_4k.png     the still
myshot_02_video_24fps.mp4      raw Higgsfield video
myshot_03_video_60fps.mp4      interpolated  ← usually the deliverable
myshot_04_video_60fps_up2x.mp4 upscaled (only with --upscale)
```

Already have a start image? Pass `--image PATH` instead of `--image-prompt` to skip
generation (and its credits).

## Spend credits deliberately — test at 5s before committing to 10s

Higgsfield video is the expensive step and it scales with duration (a 4K 10s clip
is ~2× a 5s one). The failure modes that waste money — the camera reinterpreting the
move, a background that drifts instead of staying locked, a subject's anatomy melting
— all show up in the first 5 seconds. So the default loop is:

1. Run at `--duration 5` first. Inspect stage-2's output.
2. Only if the motion reads right, rerun at `--duration 10`.

Use `--stop-after image` to eyeball the still before paying for any video, or
`--stop-after video` to skip interpolation while you're still judging the motion.

## Why the pipeline is shaped this way

**Image first, then image-to-video — never text-to-video.** A still costs a fraction
of a video, so you iterate composition cheaply and only pay the video price once the
frame is right. Text-to-video reraises the full cost on every reroll.

**8-bit H.264 High, always.** Frame-based tools drop you into a re-encode, and it's
tempting to keep 10-bit for gradient quality. Don't: `H.264 High 10` (10-bit) silently
fails to open in Windows' built-in players — the user gets "unsupported encoding". The
script forces `yuv420p` + `High` profile so every output just plays. Banding from 8-bit
is rarely visible on these gradients (they don't use the full range anyway).

**Audio is re-muxed from the source video.** RIFE and ESRGAN process image sequences
and produce silent frames. The script copies the original audio track back in during
encode, so the interpolated/upscaled clips keep their sound.

**Interpolation, not just resolution, is what reads as "premium."** Higgsfield returns
24fps. On a slow arc/orbit, 24fps judders; 60fps is what makes it feel dreamy. Reach for
`--upscale` (8K) only when the user needs crop/zoom headroom in a later edit — there are
almost no 8K displays, and on clean anime-style 4K the visible gain is small.

## Knobs

| Flag | Default | Notes |
|---|---|---|
| `--image-prompt` / `--image` | — | one is required; `--image` skips generation |
| `--motion-prompt` | — | required; the camera/subject movement |
| `--duration` | `5` | seconds; test at 5 before 10 |
| `--fps` | `60` | interpolation target |
| `--aspect` | `16:9` | e.g. `9:16` for reels |
| `--video-model` | `seedance_2_0` | 4K-native, holds background locked. `kling3_0` is cheaper but reinterprets the move more |
| `--video-res` | `4k` | `1080p` is much cheaper for drafts |
| `--rife-model` | `rife-v4.26` | under `Waifu2x-Extension-GUI/rife-ncnn-vulkan/` |
| `--upscale` | off | adds the Real-ESRGAN stage |
| `--upscale-model` | `realesr-animevideov3-x2` | anime-video model; temporally stable. `RealESRGANv2-animevideo-xsx2` also works |
| `--stop-after` | — | `image` \| `video` \| `interpolate` for cheap checkpoints |

If the Waifu2x-Extension-GUI install moves, set `W2X_DIR` in the environment; the
script globs for the engine executables inside it, so their exact suffixes don't matter.

## Designing the prompt (optional but high-leverage)

The pipeline is only as good as stage-1's composition. For scenes meant to feel
*awe-inspiring* through a camera move, the depth staging of the still is what makes or
breaks the parallax. When helping the user write the image and motion prompts, read
`references/prompt-design.md` — it covers the depth-layer method and the arc-vs-orbit
constraint that keep the background locked and the move legible.

## Requirements

- `higgsfield` CLI, authenticated (`higgsfield account status` should succeed).
- Waifu2x-Extension-GUI installed (bundles the RIFE and Real-ESRGAN NCNN engines).
- `ffmpeg` on PATH, or an interpreter with `imageio_ffmpeg`.
- An NVIDIA GPU for the local stages (tested on a 4070 Ti; 4K interpolation fits in 12 GB).
