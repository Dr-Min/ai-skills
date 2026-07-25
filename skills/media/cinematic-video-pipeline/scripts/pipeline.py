#!/usr/bin/env python3
"""
Cinematic video pipeline: image -> arc video -> 60fps interpolation -> optional upscale.

This script owns the *mechanical* pipeline only. It does NOT invent prompts —
the caller supplies the image prompt (or a ready image) and the motion prompt.

Stages:
  1. image      Generate a 4K still with Higgsfield (or reuse --image).
  2. video      Image-to-video with Higgsfield (Seedance by default), --wait.
  3. interpolate Extract frames -> RIFE (local GPU) -> re-encode 8-bit + re-mux audio.
  4. upscale    (optional) Real-ESRGAN anime-video 2x -> re-encode.

Every produced file is 8-bit H.264 High yuv420p so Windows' built-in players
open it. (10-bit H.264 / "High 10" silently fails to play on stock Windows —
that lesson is baked in here.) Audio is always re-muxed from the source video
because RIFE/ESRGAN operate on frames and drop the audio track.

Run with the interpreter that has imageio_ffmpeg available, or with ffmpeg on PATH.
"""
import argparse
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request

# --- Environment defaults. Override the local-engine dir via the W2X_DIR env var. ---
def _default_w2x_dir():
    """Best-effort auto-detect of the Waifu2x-Extension-GUI install.
    Set the W2X_DIR environment variable to point at it explicitly."""
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Programs", "Waifu2x-Extension-GUI"))
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, "Waifu2x-Extension-GUI"),
        os.path.join(home, "Downloads", "Waifu2x-Extension-GUI"),
        "/opt/Waifu2x-Extension-GUI",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0] if candidates else ""


W2X_DIR = os.environ.get("W2X_DIR") or _default_w2x_dir()
RIFE_MODEL_DEFAULT = "rife-v4.26"          # newest general model; good on fine detail
UPSCALE_MODEL_DEFAULT = "realesr-animevideov3-x2"  # temporally-aware anime-video model
IMAGE_MODEL_DEFAULT = "gpt_image_2"        # only Higgsfield image model that does 4k
VIDEO_MODEL_DEFAULT = "seedance_2_0"       # SOTA 4k-native i2v; holds the background locked


def log(msg):
    print(msg, flush=True)


def die(msg):
    print("ERROR: " + msg, file=sys.stderr, flush=True)
    sys.exit(1)


def find_ffmpeg():
    """ffmpeg on PATH, else the imageio_ffmpeg bundle, else give up with a clear message."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        die("ffmpeg not found. Put it on PATH or `pip install imageio-ffmpeg`.")


def find_exe(subdir, stem):
    """Waifu2x-Extension-GUI ships engines under inconsistent suffixes
    (rife-ncnn-vulkan_waifu2xEX.exe etc). Glob so a rename doesn't break us."""
    d = os.path.join(W2X_DIR, subdir)
    hits = glob.glob(os.path.join(d, stem + "*.exe"))
    if not hits:
        die("Missing engine: no {}*.exe under {}".format(stem, d))
    return hits[0]


def run(cmd, quiet=False):
    if not quiet:
        log("  $ " + " ".join('"{}"'.format(c) if " " in str(c) else str(c) for c in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        die("command failed ({}):\n{}".format(p.returncode, (p.stderr or p.stdout)[-2000:]))
    return p.stdout


def ffmpeg_probe_fps(ff, path):
    """Parse the source frame rate from ffmpeg's own banner ('24 fps')."""
    p = subprocess.run([ff, "-i", path], capture_output=True, text=True)
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", p.stderr)
    return float(m.group(1)) if m else 24.0


def hf_generate(model, args_list):
    """Call the Higgsfield CLI with --wait and return the result URL from stdout."""
    hf_bin = shutil.which("higgsfield") or shutil.which("higgsfield.cmd") or "higgsfield"
    cmd = [hf_bin, "generate", "create", model] + args_list + ["--wait", "--wait-timeout", "20m"]
    log("  $ higgsfield generate create {} ... --wait".format(model))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        die("higgsfield failed:\n{}".format((p.stderr or p.stdout)[-2000:]))
    urls = re.findall(r"https?://\S+", p.stdout)
    if not urls:
        die("higgsfield returned no URL. Output:\n" + p.stdout[-1000:])
    return urls[-1].strip()


def download(url, dest):
    log("  downloading -> {}".format(os.path.basename(dest)))
    urllib.request.urlretrieve(url, dest)
    return dest


def extract_frames(ff, video, outdir):
    os.makedirs(outdir, exist_ok=True)
    run([ff, "-y", "-loglevel", "error", "-i", video, os.path.join(outdir, "%08d.png")], quiet=True)
    return len(os.listdir(outdir))


def encode(ff, frame_dir, fps, audio_src, dest, ext="png", crf=16):
    """Frames -> 8-bit H.264 High, with audio copied from audio_src if it has any."""
    has_audio = "Audio:" in subprocess.run([ff, "-i", audio_src], capture_output=True, text=True).stderr
    cmd = [ff, "-y", "-loglevel", "error", "-framerate", str(fps),
           "-i", os.path.join(frame_dir, "%08d." + ext)]
    maps = ["-map", "0:v:0"]
    if has_audio:
        cmd += ["-i", audio_src]
        maps += ["-map", "1:a:0", "-c:a", "copy"]
    cmd += maps + ["-c:v", "libx264", "-crf", str(crf),
                   "-pix_fmt", "yuv420p", "-profile:v", "high", "-shortest", dest]
    run(cmd, quiet=True)
    return dest


def main():
    ap = argparse.ArgumentParser(description="Higgsfield image->video->interpolation pipeline")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image-prompt", help="prompt to generate the 4K still")
    src.add_argument("--image", help="path to an existing start image (skip generation)")
    ap.add_argument("--motion-prompt", required=True, help="camera/subject motion prompt for the video")
    ap.add_argument("--video", help="path to an existing source video (skip stage 2 generation)")
    ap.add_argument("--outdir", required=True, help="output directory (created if missing)")
    ap.add_argument("--name", default="shot", help="basename for output files")
    ap.add_argument("--duration", type=int, default=5, help="video length in seconds")
    ap.add_argument("--fps", type=int, default=60, help="interpolation target fps")
    ap.add_argument("--aspect", default="16:9", help="aspect ratio")
    ap.add_argument("--image-model", default=IMAGE_MODEL_DEFAULT)
    ap.add_argument("--video-model", default=VIDEO_MODEL_DEFAULT)
    ap.add_argument("--video-res", default="4k", help="Higgsfield video resolution")
    ap.add_argument("--rife-model", default=RIFE_MODEL_DEFAULT)
    ap.add_argument("--upscale", action="store_true", help="also produce a Real-ESRGAN upscaled version")
    ap.add_argument("--upscale-model", default=UPSCALE_MODEL_DEFAULT)
    ap.add_argument("--upscale-scale", type=int, default=2)
    ap.add_argument("--stop-after", choices=["image", "video", "interpolate"],
                    help="stop early (e.g. cheap 5s test before the 10s commit)")
    args = ap.parse_args()

    ff = find_ffmpeg()
    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.join(args.outdir, args.name)
    tmp = os.path.join(args.outdir, "_tmp")

    # 1. IMAGE ---------------------------------------------------------------
    if args.image:
        image = args.image
        log("[1/4] image: reusing {}".format(image))
    else:
        log("[1/4] image: generating 4K still ({})".format(args.image_model))
        url = hf_generate(args.image_model, [
            "--prompt", args.image_prompt, "--aspect_ratio", args.aspect,
            "--resolution", "4k", "--quality", "high"])
        image = download(url, base + "_01_reference_4k.png")
    if args.stop_after == "image":
        log("done (stopped after image): {}".format(image)); return

    # 2. VIDEO ---------------------------------------------------------------
    if args.video:
        src_video = args.video
        log("[2/4] video: reusing {}".format(src_video))
    else:
        log("[2/4] video: {} i2v {}s {}".format(args.video_model, args.duration, args.video_res))
        vargs = ["--start-image", image, "--prompt", args.motion_prompt,
                 "--aspect_ratio", args.aspect, "--resolution", args.video_res,
                 "--duration", str(args.duration)]
        if args.video_model.startswith("seedance"):
            vargs += ["--mode", "std"]
        url = hf_generate(args.video_model, vargs)
        src_video = download(url, base + "_02_video_24fps.mp4")
    if args.stop_after == "video":
        log("done (stopped after video): {}".format(src_video)); return

    # 3. INTERPOLATE ---------------------------------------------------------
    log("[3/4] interpolate: RIFE {} -> {}fps".format(args.rife_model, args.fps))
    rife = find_exe("rife-ncnn-vulkan", "rife-ncnn-vulkan")
    fin, fout = os.path.join(tmp, "in"), os.path.join(tmp, "out")
    for d in (fin, fout):
        shutil.rmtree(d, ignore_errors=True)
    n = extract_frames(ff, src_video, fin)
    src_fps = ffmpeg_probe_fps(ff, src_video)
    target = round(n * args.fps / src_fps)
    log("  {} frames @ {:.0f}fps -> {} frames @ {}fps".format(n, src_fps, target, args.fps))
    os.makedirs(fout, exist_ok=True)
    run([rife, "-i", fin, "-o", fout, "-n", str(target),
         "-m", os.path.join(W2X_DIR, "rife-ncnn-vulkan", args.rife_model), "-u", "-g", "0"], quiet=True)
    if len(os.listdir(fout)) < target * 0.9:
        die("RIFE produced too few frames ({}/{})".format(len(os.listdir(fout)), target))
    interp = encode(ff, fout, args.fps, src_video, "{}_03_video_{}fps.mp4".format(base, args.fps))
    log("  -> {}".format(interp))
    if args.stop_after == "interpolate" or not args.upscale:
        _cleanup(tmp)
        log("done: {}".format(interp)); return

    # 4. UPSCALE (optional) --------------------------------------------------
    log("[4/4] upscale: Real-ESRGAN {} x{}".format(args.upscale_model, args.upscale_scale))
    esr = find_exe("realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan")
    uin, uout = os.path.join(tmp, "uin"), os.path.join(tmp, "uout")
    for d in (uin, uout):
        shutil.rmtree(d, ignore_errors=True)
    extract_frames(ff, interp, uin)  # upscale the *interpolated* frames, not the 24fps source
    os.makedirs(uout, exist_ok=True)
    run([esr, "-i", uin, "-o", uout, "-n", args.upscale_model,
         "-s", str(args.upscale_scale), "-f", "jpg", "-g", "0"], quiet=True)
    if len(os.listdir(uout)) < 10:
        die("Real-ESRGAN produced no frames — check --upscale-model name")
    up = encode(ff, uout, args.fps, src_video,
                "{}_04_video_{}fps_up{}x.mp4".format(base, args.fps, args.upscale_scale),
                ext="jpg", crf=18)
    log("  -> {}".format(up))
    _cleanup(tmp)
    log("done: {}".format(up))


def _cleanup(tmp):
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
