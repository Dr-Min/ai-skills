#!/usr/bin/env python3
"""Export a deterministic, editor-neutral JSON or CSV timeline plan."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import stat
import sys
import unicodedata
import uuid
from fractions import Fraction
from pathlib import Path

from _cinema_common import (
    commit_temporary_file,
    contains_name_redirecting_component,
    issue,
    json_bytes,
    read_json,
)


EDITOR_BOUNDARY = (
    "Editor-neutral interchange only. Native CapCut project generation requires "
    "a separately verified adapter/schema and is not claimed by this export."
)
MAX_TIMEBASE_COMPONENT = 1_000_000_000
MAX_FRAME_NUMBER = 1_000_000_000_000
CLIP_ID_PATTERN = re.compile(r"^CLIP_[A-Z0-9_]+$")
TRACK_ID_PATTERN = re.compile(r"^TRK_[A-Z0-9_]+$")
EVENT_ID_PATTERN = re.compile(r"^EVT_[A-Z0-9_]+$")
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TIMELINE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
APPROVAL_ID_PATTERN = re.compile(r"^APR_[A-Z0-9_]+_[0-9]{3,4}$")
TIMELINE_SCHEMA_PATH_PATTERN = re.compile(
    r"^(?:\.\./)*(?:00_schemas|schemas)/timeline\.schema\.json$"
)
TIMELINE_PREDECESSOR_PATH_PATTERN = re.compile(
    r"^07_edit/(?:timeline\.json|records/[a-z][a-z0-9]*(?:_[a-z0-9]+)*/v[0-9]{3,}/timeline\.json)$"
)
RELATIVE_PATH_PATTERN = re.compile(
    r"^(?!.*(?:^|[\\/])\.\.(?:[\\/]|$))(?![A-Za-z]:)(?![\\/]).+$"
)
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SOURCE_TYPES = {"TAKE", "AUDIO", "IMAGE", "TITLE", "ADJUSTMENT"}
REVIEW_STATUSES = {
    "DRAFT",
    "INTERNAL_REVIEW",
    "USER_REVIEW_REQUIRED",
    "USER_APPROVED",
    "REJECTED",
    "SUPERSEDED",
    "EXCLUDED_FROM_INPUTS",
    "LEGACY_UNVERIFIED",
}
EVENT_TYPES = {
    "CUT",
    "TRANSITION_START",
    "TRANSITION_END",
    "MUSIC_TRANSIENT",
    "DIALOGUE_MARKER",
    "STORY_BEAT",
    "SPEED_CHANGE",
}
EVENT_SOURCES = {"MANUAL", "SYNC_CUTS_TO_MUSIC", "TIMED_STORYBOARD", "IMPORT"}
TRACK_TYPES = {"VIDEO", "AUDIO", "MUSIC", "SFX", "VOICEOVER", "GRAPHICS"}
LOCK_STATUSES = {"UNLOCKED", "PICTURE_LOCKED"}
TIMELINE_REQUIRED_FIELDS = {
    "schema_id",
    "schema_version",
    "project_id",
    "timeline_id",
    "version",
    "supersedes_timeline",
    "timebase",
    "tracks",
    "clips",
    "events",
    "lock_status",
}
TIMELINE_ALLOWED_FIELDS = TIMELINE_REQUIRED_FIELDS | {"$schema", "notes"}
TIMEBASE_FIELDS = {
    "frame_rate_numerator",
    "frame_rate_denominator",
    "drop_frame",
    "audio_sample_rate_hz",
}
TRACK_FIELDS = {"track_id", "type", "name", "order", "locked"}
PREDECESSOR_FIELDS = {"timeline_id", "version", "path", "sha256", "approval_id"}
CLIP_REQUIRED_FIELDS = {
    "clip_id",
    "track_id",
    "source_type",
    "source_id",
    "source_file",
    "source_in_frame",
    "source_out_frame",
    "timeline_in_frame",
    "timeline_out_frame",
    "speed",
    "review_status",
}
CLIP_ALLOWED_FIELDS = CLIP_REQUIRED_FIELDS | {"source_sha256", "linked_event_ids"}
EVENT_REQUIRED_FIELDS = {
    "event_id",
    "frame",
    "event_type",
    "source",
    "confidence",
    "hard_lock",
    "label",
}
EVENT_ALLOWED_FIELDS = EVENT_REQUIRED_FIELDS | {
    "time_seconds_hint",
    "source_event_id",
    "notes",
}
CSV_FIELDS = [
    "row_type",
    "clip_id",
    "track_id",
    "source_type",
    "source_id",
    "source_file",
    "source_sha256",
    "source_in_frame",
    "source_out_frame",
    "timeline_in_frame",
    "timeline_out_frame",
    "speed",
    "linked_event_ids",
    "review_status",
    "source_in_time",
    "source_out_time",
    "timeline_in_time",
    "timeline_out_time",
    "event_id",
    "frame",
    "time_seconds_hint",
    "event_type",
    "source",
    "confidence",
    "hard_lock",
    "label",
    "source_event_id",
    "notes",
    "exact_time",
    "record_json",
]


def _positive_bounded_integer(value: object, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= maximum
    )


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _nonnegative_bounded_integer(value: object, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= maximum
    )


def _finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _is_enum_string(value: object, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _time(frame: int, numerator: int, denominator: int) -> dict:
    seconds = Fraction(frame * denominator, numerator)
    return {
        "frame": frame,
        "seconds_rational": f"{seconds.numerator}/{seconds.denominator}",
        "seconds_decimal": f"{float(seconds):.9f}",
    }


def _validate(timeline: dict) -> list[dict]:
    errors: list[dict] = []
    missing = TIMELINE_REQUIRED_FIELDS - timeline.keys()
    unexpected = timeline.keys() - TIMELINE_ALLOWED_FIELDS
    if missing:
        errors.append(
            issue(
                "INVALID_TIMELINE",
                f"Timeline is missing required fields: {', '.join(sorted(missing))}",
            )
        )
    if unexpected:
        errors.append(
            issue(
                "INVALID_TIMELINE",
                f"Timeline has unsupported fields: {', '.join(sorted(unexpected))}",
            )
        )
    if timeline.get("schema_id") != "cinema-studio-pipeline/timeline@2.0.0":
        errors.append(issue("INVALID_TIMELINE", "Timeline schema_id must identify timeline@2.0.0"))
    if timeline.get("schema_version") != "2.0.0":
        errors.append(issue("INVALID_TIMELINE", "Timeline schema_version must be 2.0.0"))
    if not _matches(PROJECT_ID_PATTERN, timeline.get("project_id")):
        errors.append(issue("INVALID_TIMELINE", "Timeline project_id is invalid"))
    if not _matches(TIMELINE_ID_PATTERN, timeline.get("timeline_id")):
        errors.append(issue("INVALID_TIMELINE", "Timeline timeline_id is invalid"))
    version = timeline.get("version")
    if not _positive_integer(version):
        errors.append(issue("INVALID_TIMELINE", "Timeline version must be a positive integer"))
    if "$schema" in timeline and not _matches(
        TIMELINE_SCHEMA_PATH_PATTERN, timeline["$schema"]
    ):
        errors.append(issue("INVALID_TIMELINE", "Timeline $schema path is invalid"))
    if "notes" in timeline and not isinstance(timeline["notes"], str):
        errors.append(issue("INVALID_TIMELINE", "Timeline notes must be a string"))

    predecessor = timeline.get("supersedes_timeline")
    if _positive_integer(version) and version == 1:
        if predecessor is not None:
            errors.append(issue("INVALID_TIMELINE", "Version 1 must not supersede another timeline"))
    elif _positive_integer(version):
        if not isinstance(predecessor, dict):
            errors.append(issue("INVALID_TIMELINE", "Version 2 and later require a predecessor record"))
        else:
            predecessor_missing = PREDECESSOR_FIELDS - predecessor.keys()
            predecessor_unexpected = predecessor.keys() - PREDECESSOR_FIELDS
            if predecessor_missing or predecessor_unexpected:
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor fields do not match the schema"))
            if not _matches(TIMELINE_ID_PATTERN, predecessor.get("timeline_id")):
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor timeline_id is invalid"))
            if not _positive_integer(predecessor.get("version")):
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor version is invalid"))
            if not _matches(RELATIVE_PATH_PATTERN, predecessor.get("path")) or not _matches(
                TIMELINE_PREDECESSOR_PATH_PATTERN, predecessor.get("path")
            ):
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor path is invalid"))
            if not _matches(SHA256_PATTERN, predecessor.get("sha256")):
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor sha256 is invalid"))
            if not _matches(APPROVAL_ID_PATTERN, predecessor.get("approval_id")):
                errors.append(issue("INVALID_TIMELINE", "Timeline predecessor approval_id is invalid"))

    timebase = timeline.get("timebase")
    if not isinstance(timebase, dict):
        errors.append(issue("INVALID_TIMEBASE", "timeline.timebase must be an object"))
        return errors
    missing_timebase = TIMEBASE_FIELDS - timebase.keys()
    unexpected_timebase = timebase.keys() - TIMEBASE_FIELDS
    if missing_timebase or unexpected_timebase:
        errors.append(issue("INVALID_TIMEBASE", "Timeline timebase fields do not match the schema"))
    numerator = timebase.get("frame_rate_numerator")
    denominator = timebase.get("frame_rate_denominator")
    if not _positive_bounded_integer(
        numerator, MAX_TIMEBASE_COMPONENT
    ) or not _positive_bounded_integer(denominator, MAX_TIMEBASE_COMPONENT):
        errors.append(
            issue(
                "INVALID_TIMEBASE",
                f"Frame-rate numerator and denominator must be positive integers no greater than {MAX_TIMEBASE_COMPONENT}",
            )
        )
    if not isinstance(timebase.get("drop_frame"), bool):
        errors.append(issue("INVALID_TIMEBASE", "Timeline drop_frame must be a boolean"))
    audio_sample_rate = timebase.get("audio_sample_rate_hz")
    if (
        isinstance(audio_sample_rate, bool)
        or not isinstance(audio_sample_rate, int)
        or audio_sample_rate < 8000
    ):
        errors.append(issue("INVALID_TIMEBASE", "Timeline audio_sample_rate_hz must be an integer of at least 8000"))
    tracks = timeline.get("tracks")
    clips = timeline.get("clips")
    events = timeline.get("events")
    if not isinstance(tracks, list) or not isinstance(clips, list) or not isinstance(events, list):
        errors.append(issue("INVALID_TIMELINE", "tracks, clips, and events must be arrays"))
        return errors
    lock_status = timeline.get("lock_status", "UNLOCKED")
    if not _is_enum_string(lock_status, LOCK_STATUSES):
        errors.append(issue("INVALID_LOCK_STATUS", "Timeline lock_status must be UNLOCKED or PICTURE_LOCKED; delivery state belongs in delivery.json"))
        errors.append(issue("INVALID_TIMELINE", "Timeline lock_status does not match the schema"))
    if lock_status == "PICTURE_LOCKED":
        if not clips:
            errors.append(issue("INVALID_TIMELINE", "A PICTURE_LOCKED timeline must contain at least one clip"))
        for clip in clips:
            if isinstance(clip, dict) and (
                clip.get("review_status") != "USER_APPROVED" or not clip.get("source_sha256")
            ):
                errors.append(issue("E_UNAPPROVED_INPUT", f"Locked timeline clip is not hash-backed USER_APPROVED: {clip.get('clip_id')}"))
    track_ids: set[str] = set()
    track_orders: set[int] = set()
    for track in tracks:
        if not isinstance(track, dict):
            errors.append(issue("INVALID_TRACK", "Each track must be an object"))
            continue
        if TRACK_FIELDS - track.keys() or track.keys() - TRACK_FIELDS:
            errors.append(issue("INVALID_TRACK", "Track fields do not match the schema"))
        track_id = track.get("track_id")
        order = track.get("order")
        if not _matches(TRACK_ID_PATTERN, track_id):
            errors.append(issue("INVALID_TRACK", "Each track must have a schema-valid track_id"))
        elif track_id in track_ids:
            errors.append(issue("INVALID_TRACK", f"Duplicate track_id: {track_id}"))
        else:
            track_ids.add(track_id)
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            errors.append(issue("INVALID_TRACK", "Each track order must be a positive integer"))
        elif order in track_orders:
            errors.append(issue("INVALID_TRACK", f"Duplicate track order: {order}"))
        else:
            track_orders.add(order)
        if not _is_enum_string(track.get("type"), TRACK_TYPES):
            errors.append(issue("INVALID_TRACK", f"Track {track_id} has an invalid type"))
        name = track.get("name")
        if not isinstance(name, str) or not name:
            errors.append(issue("INVALID_TRACK", f"Track {track_id} name must be a non-empty string"))
        if not isinstance(track.get("locked"), bool):
            errors.append(issue("INVALID_TRACK", f"Track {track_id} locked must be a boolean"))
    event_ids: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            errors.append(issue("INVALID_EVENT", "Each event must be an object"))
            continue
        missing = EVENT_REQUIRED_FIELDS - event.keys()
        unexpected = event.keys() - EVENT_ALLOWED_FIELDS
        if missing:
            errors.append(
                issue(
                    "INVALID_EVENT",
                    f"Event is missing required fields: {', '.join(sorted(missing))}",
                )
            )
        if unexpected:
            errors.append(
                issue(
                    "INVALID_EVENT",
                    f"Event has unsupported fields: {', '.join(sorted(unexpected))}",
                )
            )
        event_id = event.get("event_id")
        if not _matches(EVENT_ID_PATTERN, event_id):
            errors.append(issue("INVALID_EVENT", "Each event must have a schema-valid event_id"))
        elif event_id in event_ids:
            errors.append(issue("INVALID_EVENT", f"Duplicate event_id: {event_id}"))
        else:
            event_ids.add(event_id)
        if not _nonnegative_bounded_integer(event.get("frame"), MAX_FRAME_NUMBER):
            errors.append(issue("INVALID_EVENT", "Each event must have a non-negative integer frame"))
        if not _is_enum_string(event.get("event_type"), EVENT_TYPES):
            errors.append(issue("INVALID_EVENT", f"Event {event_id} has an invalid event_type"))
        if not _is_enum_string(event.get("source"), EVENT_SOURCES):
            errors.append(issue("INVALID_EVENT", f"Event {event_id} has an invalid source"))
        confidence = event.get("confidence")
        if not _finite_number(confidence) or not 0 <= confidence <= 1:
            errors.append(issue("INVALID_EVENT", f"Event {event_id} confidence must be a finite number from 0 to 1"))
        if not isinstance(event.get("hard_lock"), bool):
            errors.append(issue("INVALID_EVENT", f"Event {event_id} hard_lock must be a boolean"))
        label = event.get("label")
        if not isinstance(label, str) or not label:
            errors.append(issue("INVALID_EVENT", f"Event {event_id} label must be a non-empty string"))
        if "time_seconds_hint" in event:
            time_hint = event["time_seconds_hint"]
            if not _finite_number(time_hint) or time_hint < 0:
                errors.append(issue("INVALID_EVENT", f"Event {event_id} time_seconds_hint must be a finite non-negative number"))
        if "source_event_id" in event and not (
            event["source_event_id"] is None
            or isinstance(event["source_event_id"], str)
        ):
            errors.append(issue("INVALID_EVENT", f"Event {event_id} source_event_id must be a string or null"))
        if "notes" in event and not isinstance(event["notes"], str):
            errors.append(issue("INVALID_EVENT", f"Event {event_id} notes must be a string"))
    clip_ids: set[str] = set()
    for clip in clips:
        if not isinstance(clip, dict):
            errors.append(issue("INVALID_CLIP", "Each clip must be an object"))
            continue
        missing = CLIP_REQUIRED_FIELDS - clip.keys()
        unexpected = clip.keys() - CLIP_ALLOWED_FIELDS
        if missing:
            errors.append(
                issue(
                    "INVALID_CLIP",
                    f"Clip is missing required fields: {', '.join(sorted(missing))}",
                )
            )
        if unexpected:
            errors.append(
                issue(
                    "INVALID_CLIP",
                    f"Clip has unsupported fields: {', '.join(sorted(unexpected))}",
                )
            )
        clip_id = clip.get("clip_id")
        if not _matches(CLIP_ID_PATTERN, clip_id):
            errors.append(issue("INVALID_CLIP", "Each clip must have a schema-valid clip_id"))
        elif clip_id in clip_ids:
            errors.append(issue("INVALID_CLIP", f"Duplicate clip_id: {clip_id}"))
        else:
            clip_ids.add(clip_id)
        clip_track_id = clip.get("track_id")
        if not _matches(TRACK_ID_PATTERN, clip_track_id):
            errors.append(issue("INVALID_CLIP", f"Clip {clip.get('clip_id')} has an invalid track_id"))
        elif clip_track_id not in track_ids:
            errors.append(issue("UNKNOWN_TRACK", f"Clip {clip.get('clip_id')} references unknown track {clip_track_id}"))
        if not _is_enum_string(clip.get("source_type"), SOURCE_TYPES):
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} has an invalid source_type"))
        source_id = clip.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} source_id must be a non-empty string"))
        if not _matches(RELATIVE_PATH_PATTERN, clip.get("source_file")):
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} has an invalid source_file"))
        source_sha256 = clip.get("source_sha256")
        if source_sha256 is not None and not _matches(SHA256_PATTERN, source_sha256):
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} source_sha256 must be a lowercase 64-character digest"))
        for prefix in ("source", "timeline"):
            start = clip.get(f"{prefix}_in_frame")
            end = clip.get(f"{prefix}_out_frame")
            if (
                not _nonnegative_bounded_integer(start, MAX_FRAME_NUMBER)
                or not _positive_bounded_integer(end, MAX_FRAME_NUMBER)
                or end <= start
            ):
                errors.append(issue("INVALID_FRAME_RANGE", f"Clip {clip.get('clip_id')} has invalid {prefix} frame range"))
                errors.append(issue("INVALID_CLIP", f"Clip {clip_id} has invalid {prefix} frame fields"))
        speed = clip.get("speed")
        if not _finite_number(speed) or speed <= 0:
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} speed must be a positive finite number"))
        linked_event_ids = clip.get("linked_event_ids", [])
        if not isinstance(linked_event_ids, list):
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} linked_event_ids must be an array"))
        else:
            seen_links: set[str] = set()
            for event_id in linked_event_ids:
                if not _matches(EVENT_ID_PATTERN, event_id):
                    errors.append(issue("INVALID_CLIP", f"Clip {clip_id} contains an invalid linked event ID"))
                elif event_id in seen_links:
                    errors.append(issue("INVALID_CLIP", f"Clip {clip_id} contains duplicate linked event {event_id}"))
                elif event_id not in event_ids:
                    errors.append(issue("UNKNOWN_EVENT", f"Clip {clip_id} references unknown event {event_id}"))
                else:
                    seen_links.add(event_id)
        if not _is_enum_string(clip.get("review_status"), REVIEW_STATUSES):
            errors.append(issue("INVALID_CLIP", f"Clip {clip_id} has an invalid review_status"))
    return errors


def _build_plan(timeline: dict) -> dict:
    timebase = timeline["timebase"]
    numerator = timebase["frame_rate_numerator"]
    denominator = timebase["frame_rate_denominator"]
    tracks = sorted(
        timeline["tracks"],
        key=lambda track: (track.get("order", 0), str(track.get("track_id", ""))),
    )
    track_order = {track["track_id"]: index for index, track in enumerate(tracks)}
    clips: list[dict] = []
    for clip in sorted(
        timeline["clips"],
        key=lambda item: (
            track_order.get(item.get("track_id"), 10**9),
            item.get("timeline_in_frame", 0),
            str(item.get("clip_id", "")),
        ),
    ):
        clips.append(
            {
                **clip,
                "source_in_time": _time(clip["source_in_frame"], numerator, denominator),
                "source_out_time": _time(clip["source_out_frame"], numerator, denominator),
                "timeline_in_time": _time(clip["timeline_in_frame"], numerator, denominator),
                "timeline_out_time": _time(clip["timeline_out_frame"], numerator, denominator),
            }
        )
    events = sorted(
        timeline["events"],
        key=lambda event: (event.get("frame", 0), str(event.get("event_id", ""))),
    )
    normalized_events = [
        {**event, "exact_time": _time(event["frame"], numerator, denominator)}
        for event in events
    ]
    duration = max(
        [clip["timeline_out_frame"] for clip in clips]
        + [event.get("frame", 0) for event in normalized_events]
        + [0]
    )
    return {
        "format": "cinema-studio-neutral-edit-plan",
        "format_version": "1.0.0",
        "editor_boundary": EDITOR_BOUNDARY,
        "source_schema_version": timeline.get("schema_version"),
        "project_id": timeline.get("project_id"),
        "timeline_id": timeline.get("timeline_id"),
        "timeline_version": timeline.get("version"),
        "timebase": {
            **timebase,
            "frame_rate_rational": f"{numerator}/{denominator}",
        },
        "duration_frames": duration,
        "duration_time": _time(duration, numerator, denominator),
        "tracks": tracks,
        "clips": clips,
        "events": normalized_events,
        "source_lock_status": timeline.get("lock_status"),
    }


def _safe_csv_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    for character in value:
        if character.isspace() or unicodedata.category(character).startswith("C"):
            continue
        return f"'{value}" if character in "=+-@" else value
    return value


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _csv_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, (dict, list)):
        value = _compact_json(value)
    return _safe_csv_cell(value)


def _stage_json(path: Path, plan: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(json_bytes(plan))
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _stage_csv(path: Path, plan: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=CSV_FIELDS,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            for row_type, records in (
                ("CLIP", plan["clips"]),
                ("EVENT", plan["events"]),
            ):
                for record in records:
                    row = {
                        field: _csv_cell(record.get(field))
                        for field in CSV_FIELDS
                        if field not in {"row_type", "record_json"}
                    }
                    row["row_type"] = row_type
                    row["record_json"] = _safe_csv_cell(_compact_json(record))
                    writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _output_error(
    source: Path,
    raw_output: Path,
    output: Path,
    *,
    force: bool,
) -> dict | None:
    if contains_name_redirecting_component(raw_output) or contains_name_redirecting_component(output):
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Output path must not contain a symlink or name-redirection: {raw_output}",
        )
    if not os.path.lexists(output):
        return None
    try:
        if not output.is_file():
            return issue(
                "UNSAFE_OUTPUT_PATH",
                f"Output target must be a regular file: {output}",
            )
        if os.path.samefile(source, output):
            return issue(
                "OUTPUT_ALIASES_INPUT",
                "Output must not alias the source timeline, even with --force",
            )
    except OSError as exc:
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Output target could not be inspected safely: {exc}",
        )
    if not force:
        return issue("OUTPUT_EXISTS", f"Refusing to overwrite existing file: {output}")
    return None


def _temporary_output_error(source: Path, temporary: Path) -> dict | None:
    if contains_name_redirecting_component(temporary):
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Staged output must not contain a symlink or name-redirection: {temporary}",
        )
    try:
        metadata = os.lstat(temporary)
        if not stat.S_ISREG(metadata.st_mode):
            return issue(
                "UNSAFE_OUTPUT_PATH",
                f"Staged output must be a regular file: {temporary}",
            )
        if os.path.samefile(source, temporary):
            return issue(
                "OUTPUT_ALIASES_INPUT",
                "Staged output must not alias the source timeline",
            )
        if getattr(metadata, "st_nlink", 1) != 1:
            return issue(
                "UNSAFE_OUTPUT_PATH",
                f"Staged output has a hardlink alias: {temporary}",
            )
    except OSError as exc:
        return issue(
            "UNSAFE_OUTPUT_PATH",
            f"Staged output could not be inspected safely: {exc}",
        )
    return None


def export_timeline(
    timeline_path: str | Path,
    output_path: str | Path,
    *,
    output_format: str | None = None,
    force: bool = False,
) -> dict:
    """Export exact frame decisions to deterministic neutral interchange."""

    raw_source = Path(timeline_path).expanduser()
    if contains_name_redirecting_component(raw_source):
        return {
            "ok": False,
            "errors": [
                issue(
                    "UNSAFE_TIMELINE_PATH",
                    f"Timeline path must not contain a symlink or name-redirection: {raw_source}",
                )
            ],
        }
    raw_output = Path(output_path).expanduser()
    if contains_name_redirecting_component(raw_output):
        return {
            "ok": False,
            "errors": [
                issue(
                    "UNSAFE_OUTPUT_PATH",
                    f"Output path must not contain a symlink or name-redirection: {raw_output}",
                )
            ],
        }
    source = raw_source.resolve()
    output = raw_output.resolve()
    if not source.is_file():
        return {"ok": False, "errors": [issue("TIMELINE_NOT_FOUND", f"Timeline not found: {source}")]}
    output_error = _output_error(source, raw_output, output, force=force)
    if output_error is not None:
        return {"ok": False, "errors": [output_error]}
    try:
        timeline = read_json(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [issue("INVALID_JSON", str(exc))]}
    if not isinstance(timeline, dict):
        return {"ok": False, "errors": [issue("INVALID_TIMELINE", "Timeline must contain an object")]}
    errors = _validate(timeline)
    if errors:
        return {"ok": False, "errors": errors}
    try:
        plan = _build_plan(timeline)
    except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "errors": [issue("INVALID_TIMELINE", f"Timeline plan could not be built safely: {exc}")],
        }
    selected_format = (output_format or output.suffix.lstrip(".") or "json").casefold()
    if selected_format not in {"json", "csv"}:
        return {"ok": False, "errors": [issue("UNSUPPORTED_FORMAT", "Use JSON or CSV. Native editor project formats require a verified adapter.")]}
    temporary: Path | None = None
    try:
        if selected_format == "json":
            temporary = _stage_json(output, plan)
        else:
            temporary = _stage_csv(output, plan)
        temporary_error = _temporary_output_error(source, temporary)
        if temporary_error is not None:
            return {"ok": False, "errors": [temporary_error]}
        if (
            contains_name_redirecting_component(raw_source)
            or contains_name_redirecting_component(source)
            or not source.is_file()
        ):
            return {
                "ok": False,
                "errors": [
                    issue(
                        "UNSAFE_TIMELINE_PATH",
                        f"Timeline path became unsafe before publish: {raw_source}",
                    )
                ],
            }
        output_error = _output_error(source, raw_output, output, force=force)
        if output_error is not None:
            return {"ok": False, "errors": [output_error]}
        temporary_error = _temporary_output_error(source, temporary)
        if temporary_error is not None:
            return {"ok": False, "errors": [temporary_error]}
        commit_temporary_file(temporary, output, force=force)
    except (OSError, UnicodeError) as exc:
        return {"ok": False, "errors": [issue("OUTPUT_WRITE_FAILED", str(exc))]}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"ok": True, "output": str(output), "format": selected_format, "clips": len(plan["clips"]), "events": len(plan["events"]), "errors": []}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeline", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--format", choices=("json", "csv"), dest="output_format")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = export_timeline(args.timeline, args.output, output_format=args.output_format, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
