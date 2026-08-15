#!/usr/bin/env python3
"""Extract deterministic PNG review frames with ffmpeg, preserving the source."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from _cinema_common import commit_temporary_file, contains_name_redirecting_component, issue
from inspect_media import (
    inspect_media,
    is_reparse_path,
    resolve_trusted_executable,
    run_process_bounded,
)


MAX_EXPLICIT_TIMES = 100
MAX_TIME_TOKEN_CHARACTERS = 64
MAX_FRAME_TIMESTAMP_SECONDS = Decimal("999999.999")
MAX_FFMPEG_STDOUT_BYTES = 64 * 1024
MAX_FFMPEG_STDERR_BYTES = 64 * 1024


def _temporary_frame_error(source: Path, temporary: Path) -> dict | None:
    if contains_name_redirecting_component(temporary):
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Temporary frame contains a symlink or name-redirection: {temporary}",
        )
    try:
        metadata = os.lstat(temporary)
        if not stat.S_ISREG(metadata.st_mode):
            return issue(
                "UNSAFE_FRAME_TARGET",
                f"Temporary frame must be a regular file: {temporary}",
            )
        if os.path.samefile(source, temporary):
            return issue(
                "OUTPUT_ALIASES_SOURCE",
                f"Temporary frame must not alias the source media: {temporary}",
            )
        if getattr(metadata, "st_nlink", 1) != 1:
            return issue(
                "UNSAFE_FRAME_TARGET",
                f"Temporary frame must not have a hardlink alias: {temporary}",
            )
    except OSError as exc:
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Temporary frame could not be inspected safely: {exc}",
        )
    return None


def _normalized_times(
    times: Iterable[float | int | str] | None,
    *,
    count: int,
    duration_seconds: float | None,
) -> tuple[list[Decimal], dict | None]:
    if times is not None:
        values: list[Decimal] = []
        try:
            for index, value in enumerate(times):
                if index >= MAX_EXPLICIT_TIMES:
                    return [], issue(
                        "INVALID_COUNT",
                        f"No more than {MAX_EXPLICIT_TIMES} explicit frame times may be requested",
                    )
                raw_value = str(value)
                if len(raw_value) > MAX_TIME_TOKEN_CHARACTERS:
                    return [], issue(
                        "INVALID_TIME",
                        f"Frame time must use no more than {MAX_TIME_TOKEN_CHARACTERS} characters",
                    )
                item = Decimal(raw_value)
                if not item.is_finite() or item < 0:
                    return [], issue("INVALID_TIME", f"Frame time must be finite and non-negative: {value!r}")
                if item > MAX_FRAME_TIMESTAMP_SECONDS:
                    return [], issue(
                        "INVALID_TIME",
                        f"Frame time exceeds the safe filename limit of {MAX_FRAME_TIMESTAMP_SECONDS} seconds: {value!r}",
                    )
                values.append(item)
        except (InvalidOperation, OverflowError, TypeError, ValueError):
            return [], issue("INVALID_TIME", "Frame times must be numeric")
        if not values:
            return [], issue("INVALID_TIME", "At least one frame time is required")
        return values, None
    if count < 1 or count > MAX_EXPLICIT_TIMES:
        return [], issue(
            "INVALID_COUNT",
            f"count must be between 1 and {MAX_EXPLICIT_TIMES}",
        )
    if duration_seconds is None:
        return [], issue("DURATION_UNKNOWN", "A positive media duration is required when --time is omitted")
    try:
        duration = Decimal(str(duration_seconds))
    except (InvalidOperation, ValueError):
        return [], issue("DURATION_UNKNOWN", "A finite positive media duration is required when --time is omitted")
    if not duration.is_finite() or duration <= 0:
        return [], issue("DURATION_UNKNOWN", "A finite positive media duration is required when --time is omitted")
    return [duration * (Decimal(index) + Decimal("0.5")) / Decimal(count) for index in range(count)], None


def _positive_duration(value: object) -> tuple[Decimal | None, dict | None]:
    try:
        duration = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None, issue(
            "DURATION_UNKNOWN", "A finite positive media duration is required"
        )
    if not duration.is_finite() or duration <= 0:
        return None, issue(
            "DURATION_UNKNOWN", "A finite positive media duration is required"
        )
    return duration, None


def _frame_name(index: int, timestamp: Decimal) -> str:
    milliseconds = int((timestamp * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"frame_{index:03d}_{milliseconds:09d}ms.png"


def _target_error(source: Path, target: Path, *, force: bool) -> dict | None:
    if contains_name_redirecting_component(target):
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Frame target path must not contain a symlink or name-redirection: {target}",
        )
    if not os.path.lexists(target):
        return None
    if is_reparse_path(target):
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Frame target must not be a symlink or reparse point: {target}",
        )
    try:
        if os.path.samefile(source, target):
            return issue(
                "OUTPUT_ALIASES_SOURCE",
                f"Frame target must not alias the source media: {target}",
            )
    except OSError:
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Frame target could not be inspected safely: {target}",
        )
    if not target.is_file():
        return issue(
            "UNSAFE_FRAME_TARGET",
            f"Frame target must be a regular file: {target}",
        )
    if not force:
        return issue("FRAME_EXISTS", f"Refusing to overwrite existing frame: {target}")
    return None


def _temporary_frame_path(target: Path) -> Path:
    return target.with_name(
        f".{target.stem}.{uuid.uuid4().hex}.tmp{target.suffix}"
    )


def extract_review_frames(
    media_path: str | Path,
    output_dir: str | Path,
    *,
    times: Iterable[float | int | str] | None = None,
    count: int = 3,
    ffmpeg_bin: str | Path | None = None,
    ffprobe_bin: str | Path | None = None,
    force: bool = False,
    timeout_seconds: float = 120.0,
) -> dict:
    """Extract frames without deleting or rewriting the source media."""

    raw_source = Path(media_path).expanduser()
    if contains_name_redirecting_component(raw_source):
        return {
            "ok": False,
            "frames": [],
            "errors": [
                issue(
                    "UNSAFE_MEDIA_PATH",
                    f"Media path must not contain a symlink or name-redirection: {raw_source}",
                )
            ],
        }
    raw_destination = Path(output_dir).expanduser()
    if contains_name_redirecting_component(raw_destination):
        return {
            "ok": False,
            "frames": [],
            "errors": [
                issue(
                    "UNSAFE_FRAME_TARGET",
                    f"Output path must not contain a symlink or name-redirection: {raw_destination}",
                )
            ],
        }
    source = raw_source.resolve()
    destination = raw_destination.resolve()
    if not source.is_file():
        return {"ok": False, "frames": [], "errors": [issue("MEDIA_NOT_FOUND", f"Media file not found: {source}")]}
    explicit_times = times is not None
    timestamps: list[Decimal] = []
    if explicit_times:
        timestamps, time_error = _normalized_times(
            times,
            count=count,
            duration_seconds=None,
        )
        if time_error:
            return {"ok": False, "frames": [], "errors": [time_error]}
    elif count < 1 or count > MAX_EXPLICIT_TIMES:
        return {
            "ok": False,
            "frames": [],
            "errors": [
                issue(
                    "INVALID_COUNT",
                    f"count must be between 1 and {MAX_EXPLICIT_TIMES}",
                )
            ],
        }
    executable = resolve_trusted_executable("ffmpeg", ffmpeg_bin)
    if executable is None:
        return {"ok": False, "frames": [], "errors": [issue("FFMPEG_NOT_FOUND", "ffmpeg was not found. Install FFmpeg or pass --ffmpeg.")]}
    targets: list[Path] = []
    if explicit_times:
        rounded_milliseconds = [
            int((timestamp * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            for timestamp in timestamps
        ]
        if len(set(rounded_milliseconds)) != len(rounded_milliseconds):
            return {"ok": False, "frames": [], "errors": [issue("DUPLICATE_FRAME_TIME", "Two requested times round to the same millisecond filename")]}
        targets = [destination / _frame_name(index, timestamp) for index, timestamp in enumerate(timestamps, 1)]
        for target in targets:
            target_error = _target_error(source, target, force=force)
            if target_error is not None:
                return {"ok": False, "frames": [], "errors": [target_error]}
    probe = inspect_media(source, ffprobe_bin=ffprobe_bin)
    if not probe.get("ok"):
        return {"ok": False, "frames": [], "errors": probe.get("errors", [issue("DURATION_UNKNOWN", "Unable to inspect media duration")])}
    duration_value = probe.get("format", {}).get("duration_seconds")
    duration, duration_error = _positive_duration(duration_value)
    if duration_error is not None or duration is None:
        return {"ok": False, "frames": [], "errors": [duration_error or issue("DURATION_UNKNOWN", "Unable to inspect media duration")]}
    if explicit_times:
        for timestamp in timestamps:
            if timestamp > duration:
                return {
                    "ok": False,
                    "frames": [],
                    "errors": [
                        issue(
                            "INVALID_TIME",
                            f"Frame time must not exceed media duration {duration}: {timestamp}",
                        )
                    ],
                }
    else:
        timestamps, time_error = _normalized_times(
            None,
            count=count,
            duration_seconds=duration_value,
        )
        if time_error:
            return {"ok": False, "frames": [], "errors": [time_error]}
        targets = [destination / _frame_name(index, timestamp) for index, timestamp in enumerate(timestamps, 1)]
        for target in targets:
            target_error = _target_error(source, target, force=force)
            if target_error is not None:
                return {"ok": False, "frames": [], "errors": [target_error]}
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "frames": [],
            "errors": [issue("OUTPUT_DIR_FAILED", str(exc), path=str(destination))],
        }
    completed_frames: list[str] = []
    for timestamp, target in zip(timestamps, targets):
        temporary = _temporary_frame_path(target)
        command = [
            str(executable),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.6f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vsync",
            "0",
            "-n",
            str(temporary),
        ]
        try:
            try:
                completed = run_process_bounded(
                    command,
                    stdout_limit=MAX_FFMPEG_STDOUT_BYTES,
                    stderr_limit=MAX_FFMPEG_STDERR_BYTES,
                    timeout_seconds=timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {"ok": False, "frames": completed_frames, "times_seconds": [float(value) for value in timestamps], "errors": [issue("FFMPEG_FAILED", str(exc), target=str(target))]}
            if completed.stdout_overflow or completed.stderr_overflow:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [
                        issue(
                            "FFMPEG_FAILED",
                            "ffmpeg output exceeds the safe capture limit",
                            target=str(target),
                        )
                    ],
                }
            if completed.returncode != 0:
                message = (completed.stderr or "ffmpeg did not create the requested frame").strip()[:2000]
                return {"ok": False, "frames": completed_frames, "times_seconds": [float(value) for value in timestamps], "errors": [issue("FFMPEG_FAILED", message, target=str(target), returncode=completed.returncode)]}
            temporary_error = _temporary_frame_error(source, temporary)
            if temporary_error is not None:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [temporary_error],
                }
            try:
                with temporary.open("r+b") as generated:
                    generated.flush()
                    os.fsync(generated.fileno())
            except OSError as exc:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [
                        issue(
                            "FRAME_PUBLISH_FAILED",
                            f"Generated frame could not be synchronized: {exc}",
                            target=str(target),
                        )
                    ],
                }
            if contains_name_redirecting_component(raw_source):
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [
                        issue(
                            "UNSAFE_MEDIA_PATH",
                            f"Media path must not contain a symlink or name-redirection: {raw_source}",
                        )
                    ],
                }
            if any(
                contains_name_redirecting_component(path)
                for path in (raw_destination, target, temporary)
            ):
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [
                        issue(
                            "UNSAFE_FRAME_TARGET",
                            f"Frame output path became unsafe before publish: {target}",
                        )
                    ],
                }
            target_error = _target_error(source, target, force=force)
            if target_error is not None:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [target_error],
                }
            temporary_error = _temporary_frame_error(source, temporary)
            if temporary_error is not None:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [temporary_error],
                }
            try:
                commit_temporary_file(temporary, target, force=force)
            except FileExistsError:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [issue("FRAME_EXISTS", f"Refusing to overwrite existing frame: {target}")],
                }
            except OSError as exc:
                return {
                    "ok": False,
                    "frames": completed_frames,
                    "times_seconds": [float(value) for value in timestamps],
                    "errors": [issue("FRAME_PUBLISH_FAILED", str(exc), target=str(target))],
                }
            completed_frames.append(str(target))
        finally:
            temporary.unlink(missing_ok=True)
    return {"ok": True, "frames": completed_frames, "times_seconds": [float(value) for value in timestamps], "errors": []}


def _parse_time_values(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--time", action="append", dest="times")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--ffmpeg", dest="ffmpeg_bin")
    parser.add_argument("--ffprobe", dest="ffprobe_bin")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = extract_review_frames(
        args.media,
        args.output_dir,
        times=_parse_time_values(args.times),
        count=args.count,
        ffmpeg_bin=args.ffmpeg_bin,
        ffprobe_bin=args.ffprobe_bin,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
