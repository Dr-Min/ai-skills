#!/usr/bin/env python3
"""Validate one spatial-control packet and its exact project-local evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - exercised by CLI environments without dependencies
    Draft202012Validator = None

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - exercised by CLI environments without dependencies
    Image = None
    UnidentifiedImageError = OSError


MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_CLEAN_MAP_PIXELS = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
PLACEHOLDER_RE = re.compile(r"(?:REPLACE_WITH|\bTBD\b|PLACEHOLDER)", re.IGNORECASE)
ENTITY_ROLES = {"CHARACTER", "PROP", "LANDMARK", "CAMERA"}
EVENT_TYPES = {"ENTRY", "EXIT", "CONTACT", "HANDOFF", "OCCLUSION", "CROSSING", "REVEAL"}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def read_json(path: Path) -> Any:
    with path.open("rb") as handle:
        payload = handle.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError(f"JSON exceeds {MAX_JSON_BYTES} bytes: {path}")
    text = payload.decode("utf-8", errors="strict")
    return json.loads(text, parse_constant=_reject_constant)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(PLACEHOLDER_RE.search(value))
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    return False


def _project_file(root: Path, raw_path: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or ":" in raw_path:
        errors.append(f"{label}: path must be a nonempty project-relative POSIX path")
        return None
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        errors.append(f"{label}: unsafe project-relative path {raw_path!r}")
        return None
    candidate = root.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        errors.append(f"{label}: path does not resolve safely inside the project: {exc}")
        return None
    if not resolved.is_file():
        errors.append(f"{label}: path is not a regular file: {raw_path}")
        return None
    return resolved


def _check_file_evidence(
    root: Path,
    evidence: Any,
    label: str,
    errors: list[str],
) -> Path | None:
    if not isinstance(evidence, dict) or set(evidence) != {"path", "sha256"}:
        errors.append(f"{label}: expected exactly path and sha256")
        return None
    digest = evidence.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        errors.append(f"{label}: sha256 must be 64 lowercase hex characters")
    path = _project_file(root, evidence.get("path"), label, errors)
    if path is not None and isinstance(digest, str) and SHA256_RE.fullmatch(digest):
        actual = sha256(path)
        if actual != digest:
            errors.append(f"{label}: declared sha256 does not match actual bytes")
    return path


def _png_dimensions(path: Path, label: str, errors: list[str]) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(33)
    except OSError as exc:
        errors.append(f"{label}: PNG header cannot be read: {exc}")
        return None
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n":
        errors.append(f"{label}: file is not a valid PNG signature/IHDR")
        return None
    length = struct.unpack(">I", header[8:12])[0]
    chunk_type = header[12:16]
    chunk_data = header[16:29]
    declared_crc = struct.unpack(">I", header[29:33])[0]
    actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
    if length != 13 or chunk_type != b"IHDR" or declared_crc != actual_crc:
        errors.append(f"{label}: file has an invalid PNG IHDR")
        return None
    width, height = struct.unpack(">II", chunk_data[:8])
    if width <= 0 or height <= 0:
        errors.append(f"{label}: PNG dimensions must be positive")
        return None
    if width * height > MAX_CLEAN_MAP_PIXELS:
        errors.append(f"{label}: PNG exceeds the {MAX_CLEAN_MAP_PIXELS}-pixel safety limit")
        return None
    return width, height


def _hex_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def _check_clean_palette(
    path: Path,
    background_color: Any,
    entities: list[Any],
    errors: list[str],
) -> None:
    if Image is None:
        errors.append("outputs.clean_map: Pillow is required to verify the geometry-only palette")
        return
    if not isinstance(background_color, str) or not COLOR_RE.fullmatch(background_color):
        errors.append("clean_map_background_color must be #RRGGBB")
        return
    required_colors: set[tuple[int, int, int]] = set()
    for entity in entities:
        if not isinstance(entity, dict) or entity.get("role") == "CAMERA":
            continue
        color = entity.get("color")
        if isinstance(color, str) and COLOR_RE.fullmatch(color):
            required_colors.add(_hex_rgb(color))
    background = _hex_rgb(background_color)
    allowed_colors = required_colors | {background}
    try:
        with Image.open(path) as image:
            image.load()
            if image.width * image.height > MAX_CLEAN_MAP_PIXELS:
                errors.append(
                    f"outputs.clean_map: PNG exceeds the {MAX_CLEAN_MAP_PIXELS}-pixel safety limit"
                )
                return
            rgba = image.convert("RGBA")
            colors = rgba.getcolors(maxcolors=MAX_CLEAN_MAP_PIXELS + 1)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        errors.append(f"outputs.clean_map: PNG pixels cannot be decoded safely: {exc}")
        return
    if colors is None:
        errors.append("outputs.clean_map: color count exceeds the geometry-palette limit")
        return
    used_colors: set[tuple[int, int, int]] = set()
    for _, (red, green, blue, alpha) in colors:
        if alpha == 0:
            continue
        if alpha != 255:
            errors.append("outputs.clean_map: semi-transparent pixels are not allowed")
            continue
        used_colors.add((red, green, blue))
    undeclared = sorted(used_colors - allowed_colors)
    if undeclared:
        preview = ", ".join(f"#{red:02X}{green:02X}{blue:02X}" for red, green, blue in undeclared[:8])
        errors.append(f"outputs.clean_map: undeclared color outside the geometry palette: {preview}")
    missing = sorted(required_colors - used_colors)
    if missing:
        preview = ", ".join(f"#{red:02X}{green:02X}{blue:02X}" for red, green, blue in missing[:8])
        errors.append(f"outputs.clean_map: entity colors are missing from the geometry map: {preview}")


def _check_point(point: Any, label: str, start: int, end: int, errors: list[str]) -> None:
    if not isinstance(point, dict):
        errors.append(f"{label}: point must be an object")
        return
    frame = point.get("frame")
    if not isinstance(frame, int) or isinstance(frame, bool) or frame < start or frame >= end:
        errors.append(f"{label}.frame: must be an integer inside [{start}, {end})")
    for axis in ("x", "y", "depth"):
        value = point.get(axis)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
            or value > 1
        ):
            errors.append(f"{label}.{axis}: must be finite and between 0 and 1")


def validate_packet(project_root: str | Path, packet_path: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    errors: list[str] = []
    checked: list[str] = []
    if not root.is_dir():
        return {"ok": False, "errors": [f"project root not found: {root}"], "checked_files": []}
    packet_file = Path(packet_path).expanduser().resolve()
    try:
        packet_file.relative_to(root)
        packet = read_json(packet_file)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"packet cannot be read safely: {exc}"], "checked_files": []}
    checked.append(packet_file.relative_to(root).as_posix())
    if not isinstance(packet, dict):
        return {"ok": False, "errors": ["packet root must be an object"], "checked_files": checked}
    if Draft202012Validator is None:
        return {
            "ok": False,
            "errors": ["jsonschema is required; install timed-storyboard/requirements.txt"],
            "checked_files": checked,
        }
    schema_path = Path(__file__).resolve().parents[1] / "references" / "spatial-control-packet.schema.json"
    try:
        schema = read_json(schema_path)
        Draft202012Validator.check_schema(schema)
        schema_errors = sorted(
            Draft202012Validator(schema).iter_errors(packet),
            key=lambda item: list(item.absolute_path),
        )
        for schema_error in schema_errors:
            location = ".".join(str(item) for item in schema_error.absolute_path) or "<root>"
            errors.append(f"schema {location}: {schema_error.message}")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "errors": [f"trusted packet schema cannot be loaded: {exc}"],
            "checked_files": checked,
        }
    if _contains_placeholder(packet):
        errors.append("packet contains an unresolved placeholder")
    if packet.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if packet.get("structural_scope_only") is not True:
        errors.append("structural_scope_only must be true")

    source_plan = _check_file_evidence(root, packet.get("source_plan"), "source_plan", errors)
    plan: dict[str, Any] | None = None
    if source_plan is not None:
        checked.append(source_plan.relative_to(root).as_posix())
        try:
            loaded = read_json(source_plan)
            if not isinstance(loaded, dict):
                errors.append("source_plan root must be an object")
            else:
                plan = loaded
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"source_plan cannot be read safely: {exc}")

    frame_range = packet.get("frame_range")
    start = frame_range.get("start_frame") if isinstance(frame_range, dict) else None
    end = frame_range.get("end_frame") if isinstance(frame_range, dict) else None
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
    ):
        errors.append("frame_range must be an ordered integer [start_frame, end_frame) range")
        start, end = 0, 1

    shot_id = packet.get("shot_id")
    if not isinstance(shot_id, str) or not shot_id:
        errors.append("shot_id is required")
    if plan is not None and isinstance(shot_id, str):
        shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
        matches = [item for item in shots if isinstance(item, dict) and item.get("id") == shot_id]
        if len(matches) != 1:
            errors.append(f"source_plan must contain exactly one shot {shot_id!r}")
        else:
            source_shot = matches[0]
            if source_shot.get("start_frame") != start or source_shot.get("end_frame") != end:
                errors.append("frame_range must exactly match the source plan shot")
        project = plan.get("project") if isinstance(plan.get("project"), dict) else {}
        if packet.get("aspect_ratio") != project.get("aspect_ratio"):
            errors.append("aspect_ratio must exactly match the source plan")

    coordinate_system = packet.get("coordinate_system")
    expected_coordinates = {
        "screen_origin": "TOP_LEFT",
        "x_range": [0, 1],
        "y_range": [0, 1],
        "depth_range": [0, 1],
        "depth_meaning": "0_NEAREST_CAMERA_1_FARTHEST_PLAYABLE_SPACE",
    }
    if coordinate_system != expected_coordinates:
        errors.append("coordinate_system must use the declared normalized camera-relative convention")

    camera = packet.get("camera")
    if not isinstance(camera, dict) or not isinstance(camera.get("axis_side"), str) or not camera.get("axis_side", "").strip():
        errors.append("camera.axis_side is required")
        camera_path: list[Any] = []
    else:
        camera_path = camera.get("path") if isinstance(camera.get("path"), list) else []
        if not isinstance(camera.get("path"), list):
            errors.append("camera.path must be an array")
    for index, point in enumerate(camera_path):
        _check_point(point, f"camera.path[{index}]", start, end, errors)

    entities = packet.get("entities")
    if not isinstance(entities, list) or not entities:
        errors.append("entities must contain at least one entity")
        entities = []
    entity_ids: set[str] = set()
    colors: set[str] = set()
    for index, entity in enumerate(entities):
        label = f"entities[{index}]"
        if not isinstance(entity, dict):
            errors.append(f"{label}: entity must be an object")
            continue
        entity_id = entity.get("entity_id")
        color = entity.get("color")
        if not isinstance(entity_id, str) or not entity_id:
            errors.append(f"{label}.entity_id is required")
        elif entity_id in entity_ids:
            errors.append(f"{label}.entity_id is duplicated: {entity_id}")
        else:
            entity_ids.add(entity_id)
        if not isinstance(color, str) or not COLOR_RE.fullmatch(color):
            errors.append(f"{label}.color must be #RRGGBB")
        elif color.lower() in colors:
            errors.append(f"{label}.color is duplicated: {color}")
        else:
            colors.add(color.lower())
        if entity.get("role") not in ENTITY_ROLES:
            errors.append(f"{label}.role is unsupported")
        states = entity.get("states")
        if not isinstance(states, list) or not states:
            errors.append(f"{label}.states must contain at least one state")
            continue
        prior_frame: int | None = None
        for state_index, state in enumerate(states):
            state_label = f"{label}.states[{state_index}]"
            _check_point(state, state_label, start, end, errors)
            if isinstance(state, dict):
                frame = state.get("frame")
                if isinstance(frame, int) and prior_frame is not None and frame < prior_frame:
                    errors.append(f"{state_label}.frame must be ordered")
                if isinstance(frame, int):
                    prior_frame = frame
                for field in ("body_facing", "head_facing", "pose_or_action_state"):
                    if not isinstance(state.get(field), str) or not state.get(field, "").strip():
                        errors.append(f"{state_label}.{field} is required")

    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        for state_index, state in enumerate(entity.get("states", [])):
            if not isinstance(state, dict):
                continue
            gaze = state.get("gaze_target_id")
            if gaze is not None and gaze not in entity_ids:
                errors.append(f"entities[{index}].states[{state_index}].gaze_target_id is unknown: {gaze}")
            occluders = state.get("occluded_by_entity_ids")
            if not isinstance(occluders, list):
                errors.append(f"entities[{index}].states[{state_index}].occluded_by_entity_ids must be an array")
            else:
                for occluder in occluders:
                    if occluder not in entity_ids:
                        errors.append(f"entities[{index}].states[{state_index}] has unknown occluder: {occluder}")

    events = packet.get("events")
    if not isinstance(events, list):
        errors.append("events must be an array")
        events = []
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        label = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{label}: event must be an object")
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            errors.append(f"{label}.event_id must be unique and nonempty")
        else:
            event_ids.add(event_id)
        if event.get("type") not in EVENT_TYPES:
            errors.append(f"{label}.type is unsupported")
        frame = event.get("frame")
        if not isinstance(frame, int) or isinstance(frame, bool) or frame < start or frame >= end:
            errors.append(f"{label}.frame must be inside [{start}, {end})")
        participants = event.get("participant_entity_ids")
        if not isinstance(participants, list) or not participants:
            errors.append(f"{label}.participant_entity_ids must be nonempty")
        elif any(item not in entity_ids for item in participants):
            errors.append(f"{label}.participant_entity_ids contains an unknown entity")

    outputs = packet.get("outputs")
    if not isinstance(outputs, dict):
        errors.append("outputs must be an object")
    else:
        review_path = _check_file_evidence(root, outputs.get("review_map"), "outputs.review_map", errors)
        clean_path = _check_file_evidence(root, outputs.get("clean_map"), "outputs.clean_map", errors)
        for output_path in (review_path, clean_path):
            if output_path is not None:
                checked.append(output_path.relative_to(root).as_posix())
                if output_path.suffix.lower() != ".png":
                    errors.append(f"control-map output must be PNG: {output_path.name}")
        if review_path is not None:
            _png_dimensions(review_path, "outputs.review_map", errors)
        clean_dimensions = (
            _png_dimensions(clean_path, "outputs.clean_map", errors)
            if clean_path is not None
            else None
        )
        aspect_ratio = packet.get("aspect_ratio")
        if clean_dimensions is not None and isinstance(aspect_ratio, str) and ":" in aspect_ratio:
            numerator_text, denominator_text = aspect_ratio.split(":", 1)
            try:
                numerator = int(numerator_text)
                denominator = int(denominator_text)
            except ValueError:
                numerator = denominator = 0
            width, height = clean_dimensions
            if numerator <= 0 or denominator <= 0 or width * denominator != height * numerator:
                errors.append(
                    "outputs.clean_map: PNG dimensions must exactly match the packet aspect_ratio"
                )
        if clean_dimensions is not None and clean_path is not None:
            _check_clean_palette(
                clean_path,
                packet.get("clean_map_background_color"),
                entities,
                errors,
            )
        if review_path is not None and clean_path is not None and review_path == clean_path:
            errors.append("review_map and clean_map must be distinct files")

    for field in ("inferred_fields", "assumptions", "failure_conditions"):
        values = packet.get(field)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            errors.append(f"{field} must be an array of nonempty strings")
        elif len(values) != len(set(values)):
            errors.append(f"{field} must not contain duplicates")

    return {"ok": not errors, "errors": errors, "checked_files": sorted(set(checked))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--packet", required=True)
    args = parser.parse_args()
    result = validate_packet(args.project_root, args.packet)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
