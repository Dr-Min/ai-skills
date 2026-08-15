#!/usr/bin/env python3
"""Read media metadata through ffprobe; never modify the source file."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from _cinema_common import (
    contains_name_redirecting_component,
    is_name_redirecting_reparse,
    issue,
)


MAX_FFPROBE_JSON_BYTES = 4 * 1024 * 1024
MAX_PROCESS_STDERR_BYTES = 64 * 1024
MAX_FRAME_RATE_COMPONENT = 1_000_000_000
_PROCESS_READ_CHUNK_BYTES = 64 * 1024
_ORIGINAL_SUBPROCESS_RUN = subprocess.run


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    stdout_overflow: bool = False
    stderr_overflow: bool = False


def _limited_bytes(value: object, limit: int) -> tuple[bytes, bool]:
    """Coerce injected-runner output without making another unbounded copy."""

    if value is None:
        return b"", False
    if isinstance(value, bytes):
        return value[:limit], len(value) > limit
    text = value if isinstance(value, str) else str(value)
    captured = bytearray()
    for offset in range(0, len(text), 4096):
        chunk = text[offset : offset + 4096].encode("utf-8", errors="replace")
        remaining = limit + 1 - len(captured)
        if remaining <= 0:
            return bytes(captured[:limit]), True
        captured.extend(chunk[:remaining])
        if len(chunk) > remaining or len(captured) > limit:
            return bytes(captured[:limit]), True
    return bytes(captured), False


def _kill_process(process: Any) -> None:
    try:
        process.kill()
    except (AttributeError, OSError, ProcessLookupError):
        pass


def _read_bounded_stream(
    stream: Any,
    *,
    limit: int,
    process: Any,
    state: dict[str, Any],
) -> None:
    captured = bytearray()
    try:
        while True:
            remaining = limit + 1 - len(captured)
            if remaining <= 0:
                state["overflow"] = True
                _kill_process(process)
                break
            chunk = stream.read(min(_PROCESS_READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", errors="replace")
            captured.extend(chunk)
            if len(captured) > limit:
                state["overflow"] = True
                _kill_process(process)
                del captured[limit:]
                break
    except (OSError, ValueError) as exc:
        state["error"] = exc
        _kill_process(process)
    finally:
        state["data"] = bytes(captured)
        try:
            stream.close()
        except (AttributeError, OSError, ValueError):
            pass


def run_process_bounded(
    command: list[str],
    *,
    stdout_limit: int,
    stderr_limit: int = MAX_PROCESS_STDERR_BYTES,
    timeout_seconds: float,
) -> BoundedProcessResult:
    """Run a process while bounding both pipe readers and killing on overflow."""

    # Keep the established injected subprocess.run seam used by callers and tests.
    # The production path below always streams from Popen with hard byte limits.
    if subprocess.run is not _ORIGINAL_SUBPROCESS_RUN:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        stdout, stdout_overflow = _limited_bytes(completed.stdout, stdout_limit)
        stderr, stderr_overflow = _limited_bytes(completed.stderr, stderr_limit)
        return BoundedProcessResult(
            returncode=completed.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            stdout_overflow=stdout_overflow,
            stderr_overflow=stderr_overflow,
        )

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        _kill_process(process)
        raise OSError("Process pipes could not be opened safely")
    stdout_state: dict[str, Any] = {"data": b"", "overflow": False}
    stderr_state: dict[str, Any] = {"data": b"", "overflow": False}
    readers = [
        threading.Thread(
            target=_read_bounded_stream,
            kwargs={
                "stream": process.stdout,
                "limit": stdout_limit,
                "process": process,
                "state": stdout_state,
            },
            daemon=True,
        ),
        threading.Thread(
            target=_read_bounded_stream,
            kwargs={
                "stream": process.stderr,
                "limit": stderr_limit,
                "process": process,
                "state": stderr_state,
            },
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process(process)
        try:
            returncode = process.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            returncode = getattr(process, "returncode", -1) or -1
    for reader in readers:
        reader.join(timeout=1.0)
    if any(reader.is_alive() for reader in readers):
        _kill_process(process)
        raise OSError("Process output readers did not terminate safely")
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout_seconds)
    for state in (stdout_state, stderr_state):
        if state.get("error") is not None:
            raise OSError(f"Process output could not be read safely: {state['error']}")
    final_returncode = getattr(process, "returncode", returncode)
    if not isinstance(final_returncode, int):
        final_returncode = returncode
    return BoundedProcessResult(
        returncode=final_returncode,
        stdout=stdout_state["data"].decode("utf-8", errors="replace"),
        stderr=stderr_state["data"].decode("utf-8", errors="replace"),
        stdout_overflow=bool(stdout_state["overflow"]),
        stderr_overflow=bool(stderr_state["overflow"]),
    )


def is_reparse_path(path: str | Path) -> bool:
    """Return whether an existing path redirects names (symlink or junction)."""

    return is_name_redirecting_reparse(path)


def _contains_reparse_component(path: Path) -> bool:
    return contains_name_redirecting_component(path)


def _ambiguous_or_script_name(path: Path) -> bool:
    name = path.name
    normalized_name = name.rstrip(" .") if os.name == "nt" else name
    if normalized_name != name:
        return True
    return Path(normalized_name).suffix.casefold() in {".bat", ".cmd"}


def _comparison_path(path: Path) -> str:
    value = os.path.normcase(os.path.normpath(str(path)))
    if os.name == "nt":
        if value.startswith("\\\\?\\unc\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return value


def _same_or_descendant(candidate: Path, root: Path) -> bool:
    candidate_value = _comparison_path(candidate)
    root_value = _comparison_path(root)
    try:
        return os.path.commonpath([candidate_value, root_value]) == root_value
    except ValueError:
        return False


def _same_or_descendant_by_file_identity(candidate: Path, root: Path) -> bool:
    current = candidate
    while True:
        try:
            if os.path.samefile(current, root):
                return True
        except OSError:
            # An implicit PATH entry that cannot be compared safely is untrusted.
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _validated_executable(path: Path) -> Path | None:
    candidate = path.expanduser()
    if _ambiguous_or_script_name(candidate):
        return None
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if _contains_reparse_component(candidate):
        return None
    try:
        metadata = os.lstat(candidate)
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if (
        not resolved.is_absolute()
        or _ambiguous_or_script_name(resolved)
        or not stat.S_ISREG(metadata.st_mode)
        or not stat.S_ISREG(os.stat(resolved).st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        return None
    return resolved


def _executable_names(command: str) -> tuple[str, ...]:
    suffix = Path(command).suffix.casefold()
    if suffix in {".bat", ".cmd"}:
        return ()
    if os.name != "nt" or suffix:
        return (command,)
    raw_extensions = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    extensions: list[str] = []
    for raw_extension in raw_extensions.split(os.pathsep):
        extension = raw_extension.strip()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension.casefold() not in {".com", ".exe"}:
            continue
        if extension.casefold() not in {item.casefold() for item in extensions}:
            extensions.append(extension)
    return tuple(f"{command}{extension}" for extension in extensions)


def resolve_trusted_executable(
    command: str,
    explicit: str | Path | None = None,
) -> Path | None:
    """Resolve an executable without implicit current-directory lookup."""

    if explicit is not None:
        return _validated_executable(Path(explicit))

    lexical_current_directory = Path.cwd().absolute()
    try:
        current_directory = lexical_current_directory.resolve(strict=True)
    except OSError:
        current_directory = lexical_current_directory
    for raw_entry in os.environ.get("PATH", "").split(os.pathsep):
        entry = raw_entry.strip().strip('"')
        if not entry:
            continue
        directory = Path(entry).expanduser()
        if not directory.is_absolute():
            continue
        if _contains_reparse_component(directory):
            continue
        if _same_or_descendant(directory, lexical_current_directory):
            continue
        try:
            resolved_directory = directory.resolve(strict=True)
        except OSError:
            continue
        if _same_or_descendant(resolved_directory, current_directory):
            continue
        if not resolved_directory.is_dir():
            continue
        if _same_or_descendant_by_file_identity(
            resolved_directory, current_directory
        ):
            continue
        for executable_name in _executable_names(command):
            resolved = _validated_executable(directory / executable_name)
            if resolved is not None:
                return resolved
    return None


def _number(value: Any, cast: type[int] | type[float]) -> int | float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = cast(value)
        if isinstance(result, float) and not math.isfinite(result):
            return None
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def _fps(value: Any) -> float | None:
    if not isinstance(value, str) or value in {"", "0/0", "N/A"}:
        return None
    try:
        fraction = Fraction(value)
        if (
            abs(fraction.numerator) > MAX_FRAME_RATE_COMPONENT
            or fraction.denominator > MAX_FRAME_RATE_COMPONENT
        ):
            return None
        result = float(fraction)
        return result if math.isfinite(result) else None
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _normalize(payload: dict, path: Path) -> dict:
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    video_streams: list[dict] = []
    audio_streams: list[dict] = []
    other_streams: list[dict] = []
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        common = {
            "index": _number(stream.get("index"), int),
            "codec": stream.get("codec_name"),
            "duration_seconds": _number(stream.get("duration"), float),
        }
        if stream.get("codec_type") == "video":
            rate = stream.get("avg_frame_rate")
            if rate in (None, "", "0/0"):
                rate = stream.get("r_frame_rate")
            video_streams.append(
                {
                    **common,
                    "width": _number(stream.get("width"), int),
                    "height": _number(stream.get("height"), int),
                    "pixel_format": stream.get("pix_fmt"),
                    "frame_rate": rate,
                    "fps": _fps(rate),
                    "frame_count": _number(stream.get("nb_frames"), int),
                    "color_space": stream.get("color_space"),
                    "color_transfer": stream.get("color_transfer"),
                    "color_primaries": stream.get("color_primaries"),
                }
            )
        elif stream.get("codec_type") == "audio":
            audio_streams.append(
                {
                    **common,
                    "sample_rate_hz": _number(stream.get("sample_rate"), int),
                    "channels": _number(stream.get("channels"), int),
                    "channel_layout": stream.get("channel_layout"),
                    "bit_rate": _number(stream.get("bit_rate"), int),
                }
            )
        else:
            other_streams.append({**common, "codec_type": stream.get("codec_type")})
    return {
        "ok": True,
        "path": str(path),
        "format": {
            "name": format_data.get("format_name"),
            "long_name": format_data.get("format_long_name"),
            "duration_seconds": _number(format_data.get("duration"), float),
            "size_bytes": _number(format_data.get("size"), int),
            "bit_rate": _number(format_data.get("bit_rate"), int),
        },
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "other_streams": other_streams,
        "errors": [],
    }


def inspect_media(
    media_path: str | Path,
    *,
    ffprobe_bin: str | Path | None = None,
    timeout_seconds: float = 60.0,
) -> dict:
    """Return normalized ffprobe metadata with dependency failures as data."""

    raw_path = Path(media_path).expanduser()
    if contains_name_redirecting_component(raw_path):
        return {
            "ok": False,
            "path": str(raw_path),
            "errors": [
                issue(
                    "UNSAFE_MEDIA_PATH",
                    f"Media path must not contain a symlink or name-redirection: {raw_path}",
                )
            ],
        }
    path = raw_path.resolve()
    if not path.is_file():
        return {"ok": False, "path": str(path), "errors": [issue("MEDIA_NOT_FOUND", f"Media file not found: {path}")]}
    executable = resolve_trusted_executable("ffprobe", ffprobe_bin)
    if executable is None:
        return {"ok": False, "path": str(path), "errors": [issue("FFPROBE_NOT_FOUND", "ffprobe was not found. Install FFmpeg or pass --ffprobe.")]}
    command = [
        str(executable),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-show_entries",
        (
            "format=format_name,format_long_name,duration,size,bit_rate:"
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,"
            "avg_frame_rate,pix_fmt,duration,sample_rate,channels,channel_layout,"
            "bit_rate,nb_frames,color_space,color_transfer,color_primaries"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = run_process_bounded(
            command,
            stdout_limit=MAX_FFPROBE_JSON_BYTES,
            timeout_seconds=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "path": str(path), "errors": [issue("FFPROBE_FAILED", str(exc))]}
    if completed.stdout_overflow:
        return {
            "ok": False,
            "path": str(path),
            "errors": [issue("FFPROBE_INVALID_JSON", "ffprobe JSON exceeds the safe output limit")],
        }
    if completed.stderr_overflow:
        return {
            "ok": False,
            "path": str(path),
            "errors": [issue("FFPROBE_FAILED", "ffprobe diagnostic output exceeds the safe output limit")],
        }
    if completed.returncode != 0:
        return {"ok": False, "path": str(path), "errors": [issue("FFPROBE_FAILED", (completed.stderr or "ffprobe failed").strip()[:2000], returncode=completed.returncode)]}
    stdout = completed.stdout
    try:
        if len(stdout.encode("utf-8", errors="replace")) > MAX_FFPROBE_JSON_BYTES:
            raise ValueError("ffprobe JSON exceeds the safe output limit")

        def reject_constant(value: str) -> None:
            raise ValueError(f"Non-finite JSON constant is forbidden: {value}")

        def finite_float(value: str) -> float:
            result = float(value)
            if not math.isfinite(result):
                raise ValueError("Non-finite JSON number is forbidden")
            return result

        payload = json.loads(
            stdout,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        return {"ok": False, "path": str(path), "errors": [issue("FFPROBE_INVALID_JSON", str(exc))]}
    if not isinstance(payload, dict):
        return {"ok": False, "path": str(path), "errors": [issue("FFPROBE_INVALID_JSON", "ffprobe returned a non-object payload")]}
    return _normalize(payload, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", nargs="+", type=Path)
    parser.add_argument("--ffprobe", dest="ffprobe_bin")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = [inspect_media(path, ffprobe_bin=args.ffprobe_bin) for path in args.media]
    print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False, indent=2))
    return 0 if all(result.get("ok") for result in results) else 2


if __name__ == "__main__":
    sys.exit(main())
