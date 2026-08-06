from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


PLAN_SCHEMA_VERSION = 1
PACKAGE_SCHEMA_VERSION = 1
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_ffmpeg(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path.resolve()
        raise FileNotFoundError(f"FFmpeg not found: {path}")
    discovered = shutil.which("ffmpeg")
    if discovered:
        return Path(discovered).resolve()
    try:
        import imageio_ffmpeg

        return Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except Exception as exc:
        raise FileNotFoundError(
            "FFmpeg was not found on PATH and imageio-ffmpeg is unavailable. "
            "Install FFmpeg or pass --ffmpeg <path>."
        ) from exc


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stderr[-5000:]}")
    return result


def decode_audio(path: Path, ffmpeg: Path, duration: float | None = None, rate: int = 44100) -> tuple[np.ndarray, int]:
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(path)]
    if duration is not None:
        command.extend(["-t", f"{duration:.6f}"])
    command.extend(["-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(rate), "pipe:1"])
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-3000:])
    audio = np.frombuffer(result.stdout, dtype="<i2").astype(np.float32) / 32768.0
    if not len(audio):
        raise ValueError(f"Decoded audio is empty: {path}")
    return audio, rate


def probe_media(path: Path, ffmpeg: Path) -> dict[str, Any]:
    result = run([str(ffmpeg), "-hide_banner", "-i", str(path), "-f", "null", "NUL" if os.name == "nt" else "/dev/null"], check=False)
    text = result.stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = None
    if duration_match:
        duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    video_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    audio_present = "Audio:" in text
    return {
        "duration": duration,
        "width": int(video_match.group(1)) if video_match else 0,
        "height": int(video_match.group(2)) if video_match else 0,
        "has_video": bool(video_match),
        "has_audio": audio_present,
    }


def compute_stft_attack(audio: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    frame_size = 1024
    hop = 128
    if len(audio) < frame_size:
        raise ValueError("Audio is too short")
    frame_count = 1 + (len(audio) - frame_size) // hop
    indices = np.arange(frame_size)[None, :] + hop * np.arange(frame_count)[:, None]
    frames = audio[indices] * np.hanning(frame_size)[None, :]
    spectrum = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_size, 1.0 / rate)
    times = (np.arange(frame_count) * hop + frame_size / 2) / rate

    band = (freqs >= 180) & (freqs <= 12000)
    log_spectrum = np.log1p(18.0 * spectrum[:, band])
    flux = np.maximum(0.0, np.diff(log_spectrum, axis=0, prepend=log_spectrum[:1])).sum(axis=1)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    rms_attack = np.maximum(0.0, np.diff(np.log1p(80.0 * rms), prepend=0.0))

    def scale(values: np.ndarray) -> np.ndarray:
        # Robust z-scores preserve the difference between a real drum attack
        # and low-level spectral chatter. A percentile-normalized 0..1 score
        # made quiet texture look like valid rapid cuts.
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median))) + 1e-9
        return np.maximum(0.0, (values - median) / (1.4826 * mad))

    attack = 0.82 * scale(flux) + 0.18 * scale(rms_attack)
    attack = np.convolve(attack, np.array([0.16, 0.68, 0.16]), mode="same")
    return spectrum, freqs, times, attack


def estimate_tempo(attack: np.ndarray, times: np.ndarray, min_bpm: float = 90, max_bpm: float = 165) -> tuple[float, list[float]]:
    if len(times) < 3:
        return 120.0, []
    envelope_rate = 1.0 / float(np.median(np.diff(times)))
    centered = attack - attack.mean()
    autocorr = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
    min_lag = max(1, int(round(envelope_rate * 60 / max_bpm)))
    max_lag = min(len(autocorr) - 1, int(round(envelope_rate * 60 / min_bpm)))
    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 * envelope_rate / lags
    prior = np.exp(-0.5 * ((bpms - 128.0) / 22.0) ** 2)
    best_lag = int(lags[np.argmax(autocorr[lags] * (0.82 + 0.18 * prior))])
    bpm = 60.0 * envelope_rate / best_lag
    phase_scores = [float(attack[phase::best_lag].sum()) for phase in range(best_lag)]
    phase = int(np.argmax(phase_scores))
    beat_times: list[float] = []
    frame = phase
    while frame < len(attack):
        left, right = max(0, frame - 2), min(len(attack), frame + 3)
        snap = left + int(np.argmax(attack[left:right]))
        beat_times.append(float(times[snap]))
        frame += best_lag
    return float(bpm), beat_times


def detect_candidates(attack: np.ndarray, times: np.ndarray, min_gap_seconds: float = 0.07) -> list[dict[str, float]]:
    local = [
        index
        for index in range(2, len(attack) - 2)
        if attack[index] == np.max(attack[index - 2 : index + 3]) and attack[index] >= 1.35
    ]
    local.sort(key=lambda index: float(attack[index]), reverse=True)
    time_step = float(np.median(np.diff(times)))
    min_gap_frames = max(1, int(round(min_gap_seconds / time_step)))
    selected: list[int] = []
    for index in local:
        if all(abs(index - chosen) >= min_gap_frames for chosen in selected):
            selected.append(index)
    selected.sort()
    max_strength = max((float(attack[index]) for index in selected), default=1.0)
    return [
        {
            "time": float(times[index]),
            "strength": float(attack[index]),
            "confidence": min(1.0, float(attack[index]) / max(1e-9, max_strength)),
        }
        for index in selected
    ]


def parse_hint(value: str) -> dict[str, float | None]:
    if ":" in value:
        start_text, end_text = value.split(":", 1)
    elif "-" in value:
        start_text, end_text = value.split("-", 1)
    else:
        start_text, end_text = value, ""
    start = float(start_text.strip())
    end = float(end_text.strip()) if end_text.strip() else None
    if start < 0 or (end is not None and end <= start):
        raise ValueError(f"Invalid hint: {value}")
    return {"start": start, "end": end}


def _nearest_beat_at_or_after(beat_times: list[float], value: float) -> float:
    later = [time_value for time_value in beat_times if time_value >= value]
    return later[0] if later else value


def select_window(
    candidates: list[dict[str, float]],
    beat_times: list[float],
    hint: dict[str, float | None],
    duration: float,
) -> dict[str, Any]:
    hint_start = float(hint["start"])
    hint_end = float(hint["end"]) if hint.get("end") is not None else None
    search_start = max(0.0, hint_start - 1.0)
    search_end = min(duration, (hint_end + 1.0) if hint_end is not None else duration)
    scoped = [item for item in candidates if search_start <= item["time"] <= search_end]
    if not scoped:
        raise ValueError(f"No transient candidates near hint {hint}")

    scoped_strengths = np.array([item["strength"] for item in scoped], dtype=np.float64)
    prominence_floor = max(1.35, float(np.percentile(scoped_strengths, 42)))
    prominent = [item for item in scoped if item["strength"] >= prominence_floor]
    if not prominent:
        prominent = scoped

    times = np.array([item["time"] for item in prominent], dtype=np.float64)
    gaps = np.diff(times, prepend=times[0] - 1.0)
    start_options = np.flatnonzero(
        (times >= hint_start - 0.70) & (times <= hint_start + 0.45) & (gaps >= 0.32)
    )
    if len(start_options):
        start_index = int(start_options[-1])
    else:
        target_beat = min(beat_times, key=lambda value: abs(value - hint_start)) if beat_times else hint_start
        nearby = np.flatnonzero((times >= hint_start - 0.25) & (times <= hint_start + 0.30))
        start_index = int(nearby[np.argmin(np.abs(times[nearby] - target_beat))]) if len(nearby) else int(np.argmin(np.abs(times - hint_start)))
    active_start = float(times[start_index])

    if hint_end is not None:
        target_release = _nearest_beat_at_or_after(beat_times, hint_end)
        release_options = np.flatnonzero((times >= hint_end - 0.10) & (times <= hint_end + 0.40))
        if len(release_options):
            release_index = int(release_options[np.argmin(np.abs(times[release_options] - target_release))])
        else:
            later = np.flatnonzero(times > hint_end)
            release_index = int(later[0]) if len(later) else len(times) - 1
        release_reason = "actual_attack_near_closed_hint"
    else:
        release_index = len(times) - 1
        for index in range(start_index + 1, len(times)):
            if times[index] - times[index - 1] >= 0.28 and times[index - 1] - active_start >= 1.0:
                release_index = index
                break
        release_reason = "first_actual_attack_after_dense_run_gap"

    release = prominent[release_index]
    active_cuts = [item for item in prominent if active_start <= item["time"] < release["time"]]
    return {
        "hint": hint,
        "search_start": search_start,
        "search_end": search_end,
        "start_detected": active_start,
        "release_detected": float(release["time"]),
        "release_strength": float(release["strength"]),
        "release_confidence": float(release["confidence"]),
        "release_reason": release_reason,
        "prominence_floor": prominence_floor,
        "cuts": active_cuts,
    }


def auto_windows(candidates: list[dict[str, float]], duration: float) -> list[dict[str, Any]]:
    if not candidates:
        return []
    groups: list[list[dict[str, float]]] = [[candidates[0]]]
    for item in candidates[1:]:
        if item["time"] - groups[-1][-1]["time"] <= 0.28:
            groups[-1].append(item)
        else:
            groups.append([item])
    windows: list[dict[str, Any]] = []
    for group in groups:
        if len(group) < 6 or group[-1]["time"] - group[0]["time"] < 0.6:
            continue
        release_time = min(duration, group[-1]["time"] + 0.20)
        windows.append(
            {
                "hint": None,
                "search_start": group[0]["time"],
                "search_end": release_time,
                "start_detected": group[0]["time"],
                "release_detected": release_time,
                "release_strength": 0.0,
                "release_confidence": 0.0,
                "release_reason": "auto_density_hold_if_no_attack",
                "cuts": group,
            }
        )
    return windows[:8]


def analyze_audio(
    audio_path: Path,
    ffmpeg: Path,
    duration: float | None,
    hints: list[dict[str, float | None]],
    fps: int,
    zoom: str,
    color: str,
    mode: str = "fill-only",
) -> tuple[dict[str, Any], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    audio, rate = decode_audio(audio_path, ffmpeg, duration)
    actual_duration = len(audio) / rate
    spectrum, freqs, times, attack = compute_stft_attack(audio, rate)
    bpm, beat_times = estimate_tempo(attack, times)
    candidates = detect_candidates(attack, times)
    windows = [select_window(candidates, beat_times, hint, actual_duration) for hint in hints] if hints else auto_windows(candidates, actual_duration)

    for window_index, window in enumerate(windows, start=1):
        for cut in window["cuts"]:
            frame = int(math.ceil(cut["time"] * fps - 1e-9))
            cut["render_frame"] = frame
            cut["render_time"] = frame / fps
        release_frame = int(math.ceil(window["release_detected"] * fps - 1e-9))
        window["release_frame"] = release_frame
        window["release_render_time"] = release_frame / fps
        window["index"] = window_index

    cuts = sorted(
        [dict(cut, window=window["index"]) for window in windows for cut in window["cuts"]],
        key=lambda item: item["render_frame"],
    )
    total_frames = int(round(actual_duration * fps))
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "created_utc": utc_now(),
        "audio": {
            "path": str(audio_path.resolve()),
            "sha256": sha256(audio_path),
            "duration_seconds": actual_duration,
            "sample_rate": rate,
        },
        "settings": {
            "mode": mode,
            "fps": fps,
            "zoom": zoom,
            "color": color,
            "flash": False,
            "release_policy": "next_actual_attack_or_hold",
            "hints": hints,
        },
        "analysis": {
            "estimated_bpm": bpm,
            "candidate_count": len(candidates),
            "candidate_times": candidates,
            "frequency_band_hz": [180, 12000],
            "stft": {"frame_size": 1024, "hop": 128},
        },
        "windows": windows,
        "timeline": {
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": total_frames / fps,
            "cuts": cuts,
            "cut_frames": sorted({int(cut["render_frame"]) for cut in cuts if 0 < cut["render_frame"] < total_frames}),
        },
        "status": "diagnostic_review_required",
    }
    return plan, (spectrum, freqs, times, attack)


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "audio", "settings", "analysis", "windows", "timeline", "status"):
        if key not in plan:
            errors.append(f"missing top-level field: {key}")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        errors.append(f"unsupported plan schema: {plan.get('schema_version')}")
    timeline = plan.get("timeline") or {}
    frames = timeline.get("cut_frames") or []
    if frames != sorted(set(frames)):
        errors.append("cut_frames must be unique and sorted")
    total = int(timeline.get("total_frames") or 0)
    if any(frame <= 0 or frame >= total for frame in frames):
        errors.append("cut frame outside timeline")
    return errors


def load_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_plan(plan)
    if errors:
        raise ValueError("Invalid cut plan: " + "; ".join(errors))
    return plan


def write_json(path: Path, value: Any, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8-sig" if bom else "utf-8")


def zoom_amount(name: str) -> float:
    return {"off": 0.0, "subtle": 0.03, "medium": 0.06, "strong": 0.10}[name]


def render_package(
    plan_path: Path,
    audio_path: Path,
    media_paths: list[Path],
    output_dir: Path,
    ffmpeg: Path,
    width: int = 1280,
    height: int = 720,
    diagnostic_path: Path | None = None,
) -> Path:
    plan = load_plan(plan_path)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite: {output_dir}")
    for path in [audio_path, *media_paths]:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not media_paths:
        raise ValueError("At least one media file is required")
    if diagnostic_path is not None and not diagnostic_path.is_file():
        raise FileNotFoundError(diagnostic_path)

    stage = output_dir.with_name(output_dir.name + ".__building__")
    if stage.exists():
        raise FileExistsError(stage)
    clips_dir = stage / "01_video_clips"
    audio_dir = stage / "02_audio"
    reference_dir = stage / "03_reference"
    timing_dir = stage / "04_timing"
    for directory in (clips_dir, audio_dir, reference_dir, timing_dir):
        directory.mkdir(parents=True, exist_ok=False)

    fps = int(plan["timeline"]["fps"])
    total_frames = int(plan["timeline"]["total_frames"])
    boundaries = [0, *plan["timeline"]["cut_frames"], total_frames]
    boundaries = sorted(set(int(value) for value in boundaries))
    media_info = [probe_media(path, ffmpeg) for path in media_paths]
    source_offsets = [0.0 for _ in media_paths]
    media_index = 0
    rows: list[dict[str, Any]] = []
    z_amount = zoom_amount(plan["settings"]["zoom"])
    color_mode = plan["settings"]["color"]

    for clip_no, (start_frame, end_frame) in enumerate(zip(boundaries[:-1], boundaries[1:]), start=1):
        if clip_no > 1:
            media_index = (media_index + 1) % len(media_paths)
        source = media_paths[media_index]
        frame_count = end_frame - start_frame
        duration = frame_count / fps
        info = media_info[media_index]
        source_offset = source_offsets[media_index]
        if info.get("duration"):
            source_offset %= float(info["duration"])
        source_offsets[media_index] += duration

        output = clips_dir / f"cut_{clip_no:03d}.mp4"
        command = [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error"]
        if source.suffix.lower() in IMAGE_EXTENSIONS:
            command.extend(["-loop", "1", "-i", str(source)])
        else:
            command.extend(["-stream_loop", "-1", "-ss", f"{source_offset:.6f}", "-i", str(source)])

        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            f"fps={fps}",
        ]
        if color_mode == "cycle" and clip_no > 1:
            style = clip_no % 4
            if style == 1:
                filters.append("eq=saturation=1.22:contrast=1.06")
            elif style == 2:
                filters.append("colorbalance=rs=.08:bs=.10")
            elif style == 3:
                filters.append("hue=s=0")
        if z_amount > 0 and clip_no > 1:
            denominator = max(1, frame_count - 1)
            filters.append(
                "zoompan="
                f"z='min(1+{z_amount:.6f}*on/{denominator},1+{z_amount:.6f})':"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d=1:s={width}x{height}:fps={fps}"
            )
        filters.append("format=yuv420p")
        command.extend(
            [
                "-an", "-vf", ",".join(filters),
                "-frames:v", str(frame_count),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-threads", "4",
                "-pix_fmt", "yuv420p", str(output),
            ]
        )
        run(command)
        rows.append(
            {
                "clip_no": clip_no,
                "filename": output.name,
                "start_frame": start_frame,
                "end_frame_exclusive": end_frame,
                "frame_count": frame_count,
                "start_sec": start_frame / fps,
                "end_sec": end_frame / fps,
                "duration_sec": duration,
                "media_index": media_index + 1,
                "source_path": str(source.resolve()),
                "source_start_sec": source_offset,
                "zoom": plan["settings"]["zoom"] if clip_no > 1 else "off",
                "color": color_mode if clip_no > 1 else "off",
            }
        )

    concat_path = timing_dir / "concat_list.txt"
    concat_path.write_text("\n".join(f"file '../01_video_clips/{row['filename']}'" for row in rows) + "\n", encoding="utf-8")
    visual = reference_dir / "visual_only.mp4"
    run([str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", str(visual)])

    continuous_audio = audio_dir / "music_continuous.wav"
    run(
        [
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio_path),
            "-t", f"{total_frames / fps:.6f}", "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(continuous_audio),
        ]
    )
    reference = reference_dir / "reference.mp4"
    run(
        [
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-i", str(visual), "-i", str(continuous_audio),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            str(reference),
        ]
    )

    with (timing_dir / "cut_timeline.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    shutil.copy2(plan_path, timing_dir / "cut_plan.json")
    if diagnostic_path is not None:
        shutil.copy2(diagnostic_path, timing_dir / "cut_diagnostic.png")

    ffmpeg_version = run([str(ffmpeg), "-version"], check=False).stdout.splitlines()

    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "created_utc": utc_now(),
        "fps": fps,
        "width": width,
        "height": height,
        "total_frames": total_frames,
        "duration_seconds": total_frames / fps,
        "clip_count": len(rows),
        "placement": "round_robin_continuous_source_progression",
        "ffmpeg": {
            "path": str(ffmpeg),
            "version": ffmpeg_version[0] if ffmpeg_version else "unknown",
        },
        "diagnostic": (
            {"path": "04_timing/cut_diagnostic.png", "sha256": sha256(timing_dir / "cut_diagnostic.png")}
            if diagnostic_path is not None
            else None
        ),
        "audio": {"path": str(continuous_audio.relative_to(stage)), "sha256": sha256(continuous_audio)},
        "reference": {"path": str(reference.relative_to(stage)), "sha256": sha256(reference)},
        "clips": [
            {
                **row,
                "path": str((clips_dir / row["filename"]).relative_to(stage)),
                "bytes": (clips_dir / row["filename"]).stat().st_size,
                "sha256": sha256(clips_dir / row["filename"]),
            }
            for row in rows
        ],
        "sources": [{"path": str(path.resolve()), "sha256": sha256(path)} for path in media_paths],
        "verification": {"frame_sum": sum(row["frame_count"] for row in rows), "nonempty_clips": all((clips_dir / row["filename"]).stat().st_size > 0 for row in rows)},
    }
    write_json(timing_dir / "package_manifest.json", manifest)
    (stage / "IMPORT_KO.txt").write_text(
        "CapCut에서 01_video_clips의 파일을 이름순으로 모두 메인 트랙에 놓고, "
        "02_audio/music_continuous.wav를 0초에 놓으세요. JSON 모드는 이 배치를 자동 생성합니다.\n",
        encoding="utf-8-sig",
    )
    stage.rename(output_dir)
    return output_dir


def _new_id() -> str:
    return str(uuid.uuid4()).upper()


def _replace_path_strings(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_path_strings(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_path_strings(item, old, new) for key, item in value.items()}
    return value


def export_capcut_json(package_dir: Path, template_draft: Path, output_draft: Path) -> Path:
    if output_draft.exists():
        raise FileExistsError(f"Refusing to overwrite: {output_draft}")
    manifest_path = package_dir / "04_timing" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content_path = template_draft / "draft_content.json"
    meta_path = template_draft / "draft_meta_info.json"
    if not content_path.is_file() or not meta_path.is_file():
        raise FileNotFoundError("Template draft must contain draft_content.json and draft_meta_info.json")

    stage = output_draft.with_name(output_draft.name + ".__building__")
    if stage.exists():
        raise FileExistsError(stage)
    shutil.copytree(template_draft, stage)
    locked = stage / ".locked"
    if locked.exists():
        locked.unlink()

    content = json.loads((stage / "draft_content.json").read_text(encoding="utf-8"))
    materials = content.get("materials") or {}
    videos = materials.get("videos") or []
    audios = materials.get("audios") or []
    tracks = content.get("tracks") or []
    video_track = next((track for track in tracks if track.get("type") == "video" and track.get("segments")), None)
    audio_track = next((track for track in tracks if track.get("type") == "audio" and track.get("segments")), None)
    if not videos or not audios or video_track is None or audio_track is None:
        raise ValueError("Template draft requires at least one video segment and one audio segment")

    video_material_proto = videos[0]
    audio_material_proto = audios[0]
    video_segment_proto = video_track["segments"][0]
    audio_segment_proto = audio_track["segments"][0]
    fps = int(manifest["fps"])
    new_video_materials: list[dict[str, Any]] = []
    new_video_segments: list[dict[str, Any]] = []

    for clip in manifest["clips"]:
        clip_path = (package_dir / clip["path"]).resolve()
        duration_us = int(round(int(clip["frame_count"]) / fps * 1_000_000))
        material = copy.deepcopy(video_material_proto)
        material_id = _new_id()
        for key in ("id", "local_id", "material_id", "unique_id", "origin_material_id"):
            if key in material:
                material[key] = material_id
        for key in ("path", "media_path"):
            if key in material:
                material[key] = str(clip_path)
        material["material_name"] = clip_path.name
        material["duration"] = duration_us
        material["width"] = int(manifest["width"])
        material["height"] = int(manifest["height"])
        material["has_audio"] = False
        new_video_materials.append(material)

        segment = copy.deepcopy(video_segment_proto)
        segment_id = _new_id()
        segment["id"] = segment_id
        if "raw_segment_id" in segment:
            segment["raw_segment_id"] = segment_id
        segment["material_id"] = material_id
        start_us = int(round(float(clip["start_frame"]) / fps * 1_000_000))
        segment["source_timerange"] = {"start": 0, "duration": duration_us}
        segment["target_timerange"] = {"start": start_us, "duration": duration_us}
        if "render_timerange" in segment:
            segment["render_timerange"] = {"start": start_us, "duration": duration_us}
        if isinstance(segment.get("clip"), dict):
            segment["clip"]["scale"] = {"x": 1.0, "y": 1.0}
            segment["clip"]["alpha"] = 1.0
        new_video_segments.append(segment)

    audio_path = (package_dir / manifest["audio"]["path"]).resolve()
    total_us = int(round(float(manifest["duration_seconds"]) * 1_000_000))
    audio_material = copy.deepcopy(audio_material_proto)
    audio_id = _new_id()
    for key in ("id", "local_id", "material_id", "unique_id"):
        if key in audio_material:
            audio_material[key] = audio_id
    audio_material["path"] = str(audio_path)
    audio_material["name"] = audio_path.name
    audio_material["duration"] = total_us
    audio_segment = copy.deepcopy(audio_segment_proto)
    audio_segment_id = _new_id()
    audio_segment["id"] = audio_segment_id
    if "raw_segment_id" in audio_segment:
        audio_segment["raw_segment_id"] = audio_segment_id
    audio_segment["material_id"] = audio_id
    audio_segment["source_timerange"] = {"start": 0, "duration": total_us}
    audio_segment["target_timerange"] = {"start": 0, "duration": total_us}
    if "render_timerange" in audio_segment:
        audio_segment["render_timerange"] = {"start": 0, "duration": total_us}

    materials["videos"] = new_video_materials
    materials["audios"] = [audio_material]
    content["materials"] = materials
    video_track_copy = copy.deepcopy(video_track)
    audio_track_copy = copy.deepcopy(audio_track)
    video_track_copy["id"] = _new_id()
    video_track_copy["segments"] = new_video_segments
    audio_track_copy["id"] = _new_id()
    audio_track_copy["segments"] = [audio_segment]
    content["tracks"] = [video_track_copy, audio_track_copy]
    content["duration"] = total_us
    content["fps"] = float(fps)
    content["id"] = _new_id()
    content["name"] = output_draft.name
    content["path"] = str(output_draft)
    content["update_time"] = int(time.time())

    serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    for name in ("draft_content.json", "draft_content.json.bak", "template-2.tmp"):
        target = stage / name
        if target.exists() or name == "draft_content.json":
            target.write_text(serialized, encoding="utf-8")

    meta = json.loads((stage / "draft_meta_info.json").read_text(encoding="utf-8"))
    meta = _replace_path_strings(meta, str(template_draft), str(output_draft))
    meta["draft_name"] = output_draft.name
    meta["draft_id"] = content["id"]
    meta["draft_fold_path"] = str(output_draft)
    meta["draft_root_path"] = str(output_draft.parent)
    meta["draft_new_version"] = str(content.get("new_version", meta.get("draft_new_version", "")))
    meta["tm_duration"] = total_us
    meta["tm_draft_modified"] = int(time.time())

    material_groups = meta.get("draft_materials") or []
    group_zero = next((group for group in material_groups if group.get("type") == 0), None)
    if group_zero is not None and group_zero.get("value"):
        proto = group_zero["value"][0]
        summaries: list[dict[str, Any]] = []
        for clip in manifest["clips"]:
            path = (package_dir / clip["path"]).resolve()
            item = copy.deepcopy(proto)
            item["id"] = _new_id()
            item["file_Path"] = str(path)
            item["metetype"] = "video"
            item["duration"] = int(round(int(clip["frame_count"]) / fps * 1_000_000))
            item["width"] = int(manifest["width"])
            item["height"] = int(manifest["height"])
            item["md5"] = md5(path)
            summaries.append(item)
        audio_item = copy.deepcopy(proto)
        audio_item["id"] = _new_id()
        audio_item["file_Path"] = str(audio_path)
        audio_item["metetype"] = "music"
        audio_item["duration"] = total_us
        audio_item["width"] = 0
        audio_item["height"] = 0
        audio_item["md5"] = md5(audio_path)
        summaries.append(audio_item)
        group_zero["value"] = summaries
    write_json(stage / "draft_meta_info.json", meta)

    validation = validate_capcut_stage(stage)
    write_json(stage / "sync_cuts_validation.json", validation)
    if not validation["ok"]:
        raise RuntimeError("Staged CapCut draft failed validation: " + "; ".join(validation["errors"]))
    stage.rename(output_draft)
    return output_draft


def validate_capcut_stage(draft_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"draft_content parse failed: {exc}"]}
    materials = content.get("materials") or {}
    video_ids = {item.get("id") for item in materials.get("videos") or []}
    audio_ids = {item.get("id") for item in materials.get("audios") or []}
    video_track = next((track for track in content.get("tracks") or [] if track.get("type") == "video"), None)
    audio_track = next((track for track in content.get("tracks") or [] if track.get("type") == "audio"), None)
    if video_track is None or audio_track is None:
        errors.append("missing video or audio track")
    video_segments = video_track.get("segments") or [] if video_track else []
    audio_segments = audio_track.get("segments") or [] if audio_track else []
    if any(segment.get("material_id") not in video_ids for segment in video_segments):
        errors.append("unresolved video material reference")
    if any(segment.get("material_id") not in audio_ids for segment in audio_segments):
        errors.append("unresolved audio material reference")
    ranges = sorted((int(seg["target_timerange"]["start"]), int(seg["target_timerange"]["duration"])) for seg in video_segments)
    cursor = 0
    for start, duration in ranges:
        if abs(start - cursor) > 1:
            errors.append(f"timeline gap or overlap at {cursor}->{start}")
            break
        cursor = start + duration
    if abs(cursor - int(content.get("duration") or 0)) > 1:
        errors.append("video timeline duration mismatch")
    missing_media = [item.get("path") for item in materials.get("videos") or [] if item.get("path") and not Path(item["path"]).is_file()]
    missing_media += [item.get("path") for item in materials.get("audios") or [] if item.get("path") and not Path(item["path"]).is_file()]
    if missing_media:
        errors.append(f"missing media files: {len(missing_media)}")
    return {
        "ok": not errors,
        "errors": errors,
        "video_materials": len(video_ids),
        "video_segments": len(video_segments),
        "audio_materials": len(audio_ids),
        "audio_segments": len(audio_segments),
        "duration": content.get("duration"),
    }


def verify_package(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "04_timing" / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    clips = manifest.get("clips") or []
    frame_sum = 0
    for clip in clips:
        path = package_dir / clip["path"]
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty clip: {path}")
            continue
        if sha256(path) != clip["sha256"]:
            errors.append(f"clip hash mismatch: {path.name}")
        frame_sum += int(clip["frame_count"])
    if frame_sum != int(manifest["total_frames"]):
        errors.append(f"frame sum mismatch: {frame_sum} != {manifest['total_frames']}")
    audio = package_dir / manifest["audio"]["path"]
    if not audio.is_file() or sha256(audio) != manifest["audio"]["sha256"]:
        errors.append("audio missing or hash mismatch")
    reference = package_dir / manifest["reference"]["path"]
    if not reference.is_file() or sha256(reference) != manifest["reference"]["sha256"]:
        errors.append("reference missing or hash mismatch")
    return {"ok": not errors, "errors": errors, "clip_count": len(clips), "frame_sum": frame_sum, "total_frames": manifest["total_frames"], "duration_seconds": manifest["duration_seconds"]}
