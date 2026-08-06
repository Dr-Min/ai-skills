#!/usr/bin/env python3
"""Initialize, validate, and export timed storyboard project plans."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
ALLOWED_TRANSITIONS = {"none", "cut", "dissolve", "fade", "match_cut", "wipe"}
ALLOWED_STATUSES = {
    "planned",
    "timing_approved",
    "rough_generated",
    "rough_approved",
    "detailed_generated",
    "approved",
    "rejected",
}
SPATIAL_CAMERA_MODES = {
    "dolly_in",
    "dolly_out",
    "truck_left",
    "truck_right",
    "crane_up",
    "crane_down",
    "arc",
    "handheld_follow",
    "locked_subject_tracking",
}
ALLOWED_CAMERA_MODES = SPATIAL_CAMERA_MODES | {"static", "pan", "tilt"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("plan root must be a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_seconds(frame: int, fps: int) -> str:
    return f"{frame / fps:.3f}"


def new_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "title": args.title,
            "duration_seconds": args.duration,
            "fps": args.fps,
            "aspect_ratio": args.aspect_ratio,
            "default_roughness_level": args.level,
            "timing_mode": args.timing_mode,
        },
        "story_contract": {
            "cause": "",
            "goal": "",
            "stakes": "",
            "obstacle": "",
            "discovery": "",
            "choice": "",
        },
        "continuity": {
            "characters": {},
            "locations": {},
            "props": {},
            "screen_direction": "",
        },
        "scenes": [],
        "shots": [],
    }


def validate_path(
    path: Any,
    label: str,
    shot_start: int,
    shot_end: int,
    errors: list[str],
) -> None:
    if not isinstance(path, list):
        errors.append(f"{label}: path must be a list")
        return
    prior_frame: int | None = None
    for index, point in enumerate(path):
        point_label = f"{label}.path[{index}]"
        if not isinstance(point, dict):
            errors.append(f"{point_label}: waypoint must be an object")
            continue
        frame = point.get("frame")
        x = point.get("x")
        y = point.get("y")
        if not isinstance(frame, int):
            errors.append(f"{point_label}: frame must be an integer")
        else:
            if frame < shot_start or frame > shot_end:
                errors.append(
                    f"{point_label}: frame {frame} falls outside shot "
                    f"[{shot_start}, {shot_end}]"
                )
            if prior_frame is not None and frame < prior_frame:
                errors.append(f"{point_label}: waypoint frames must be ordered")
            prior_frame = frame
        for axis, value in (("x", x), ("y", y)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{point_label}: {axis} must be numeric")
            elif value < 0 or value > 1:
                errors.append(f"{point_label}: {axis} must be between 0 and 1")


def validate_phases(
    phases: Any,
    label: str,
    shot_start: int,
    shot_end: int,
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(phases, list):
        errors.append(f"{label}: action_phases must be a list")
        return
    if not phases:
        warnings.append(f"{label}: action_phases is empty")
        return
    prior_end = shot_start
    for index, phase in enumerate(phases):
        phase_label = f"{label}.action_phases[{index}]"
        if not isinstance(phase, dict):
            errors.append(f"{phase_label}: phase must be an object")
            continue
        start = phase.get("start_frame")
        end = phase.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(f"{phase_label}: start_frame and end_frame must be integers")
            continue
        if start < shot_start or end > shot_end or start >= end:
            errors.append(
                f"{phase_label}: invalid range [{start}, {end}) for shot "
                f"[{shot_start}, {shot_end})"
            )
        if start < prior_end:
            errors.append(f"{phase_label}: phase overlaps the previous phase")
        elif start > prior_end:
            warnings.append(f"{phase_label}: unassigned action gap before frame {start}")
        prior_end = max(prior_end, end)
        for field in ("name", "pose", "action", "gaze", "speed"):
            if not str(phase.get(field, "")).strip():
                warnings.append(f"{phase_label}: missing visible {field}")
    if prior_end < shot_end:
        warnings.append(f"{label}: action phases end at {prior_end}, before shot end {shot_end}")


def validate_plan(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    project = plan.get("project")
    if not isinstance(project, dict):
        return ["project must be an object"], warnings

    fps = project.get("fps")
    duration = project.get("duration_seconds")
    level = project.get("default_roughness_level")
    if not isinstance(fps, int) or fps <= 0:
        errors.append("project.fps must be a positive integer")
        fps = 24
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        errors.append("project.duration_seconds must be positive")
        duration = 0
    if level not in {1, 2, 3, 4}:
        errors.append("project.default_roughness_level must be 1, 2, 3, or 4")

    story_contract = plan.get("story_contract", {})
    if not isinstance(story_contract, dict):
        errors.append("story_contract must be an object")
    else:
        for field in ("cause", "goal", "stakes", "obstacle", "discovery", "choice"):
            if not str(story_contract.get(field, "")).strip():
                warnings.append(f"story_contract.{field} is unresolved")

    shots = plan.get("shots")
    if not isinstance(shots, list):
        return errors + ["shots must be a list"], warnings
    if not shots:
        warnings.append("shots is empty")
        return errors, warnings

    seen_ids: set[str] = set()
    sortable: list[tuple[int, int, str, dict[str, Any]]] = []

    for index, shot in enumerate(shots):
        label = f"shots[{index}]"
        if not isinstance(shot, dict):
            errors.append(f"{label}: shot must be an object")
            continue
        shot_id = str(shot.get("id", "")).strip()
        if not shot_id:
            errors.append(f"{label}: id is required")
            shot_id = label
        elif shot_id in seen_ids:
            errors.append(f"{label}: duplicate id {shot_id}")
        seen_ids.add(shot_id)

        start = shot.get("start_frame")
        end = shot.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(f"{shot_id}: start_frame and end_frame must be integers")
            continue
        if start < 0 or end <= start:
            errors.append(f"{shot_id}: invalid frame range [{start}, {end})")
        total_frames = round(float(duration) * fps)
        if end > total_frames:
            errors.append(f"{shot_id}: end_frame {end} exceeds project frame {total_frames}")
        sortable.append((start, end, shot_id, shot))

        story = shot.get("story")
        if not isinstance(story, dict):
            errors.append(f"{shot_id}: story must be an object")
        else:
            if not str(story.get("purpose", "")).strip():
                warnings.append(f"{shot_id}: story purpose is missing")
            if not str(story.get("visible_change", "")).strip():
                warnings.append(f"{shot_id}: visible_change is missing")

        for side in ("transition_in", "transition_out"):
            transition = shot.get(side, "none")
            if transition not in ALLOWED_TRANSITIONS:
                errors.append(f"{shot_id}: unsupported {side} {transition!r}")

        board = shot.get("board")
        if not isinstance(board, dict):
            errors.append(f"{shot_id}: board must be an object")
        else:
            shot_level = board.get("roughness_level", level)
            if shot_level not in {1, 2, 3, 4}:
                errors.append(f"{shot_id}: board.roughness_level must be 1-4")
            status = board.get("status", "planned")
            if status not in ALLOWED_STATUSES:
                errors.append(f"{shot_id}: unsupported board.status {status!r}")
            if shot_level == 4 and board.get("annotation_mode") == "inline":
                warnings.append(
                    f"{shot_id}: Level 4 should preserve a clean still and use a companion annotation card"
                )

        characters = shot.get("characters", [])
        if not isinstance(characters, list):
            errors.append(f"{shot_id}: characters must be a list")
        else:
            for character_index, character in enumerate(characters):
                char_label = f"{shot_id}.characters[{character_index}]"
                if not isinstance(character, dict):
                    errors.append(f"{char_label}: character must be an object")
                    continue
                if not str(character.get("character_id", "")).strip():
                    errors.append(f"{char_label}: character_id is required")
                stationary = character.get("stationary")
                path = character.get("path", [])
                validate_path(path, char_label, start, end, errors)
                if stationary is False and len(path) < 2:
                    errors.append(f"{char_label}: moving character requires at least two path waypoints")
                if stationary is True and path:
                    warnings.append(f"{char_label}: stationary character has travel waypoints")
                if not str(character.get("start_pose", "")).strip():
                    warnings.append(f"{char_label}: start_pose is missing")
                if not str(character.get("end_pose", "")).strip():
                    warnings.append(f"{char_label}: end_pose is missing")
                validate_phases(
                    character.get("action_phases", []),
                    char_label,
                    start,
                    end,
                    errors,
                    warnings,
                )

        props = shot.get("props", [])
        if not isinstance(props, list):
            errors.append(f"{shot_id}: props must be a list")
        else:
            for prop_index, prop in enumerate(props):
                prop_label = f"{shot_id}.props[{prop_index}]"
                if not isinstance(prop, dict):
                    errors.append(f"{prop_label}: prop must be an object")
                    continue
                if not str(prop.get("prop_id", "")).strip():
                    errors.append(f"{prop_label}: prop_id is required")
                prop_path = prop.get("path", [])
                validate_path(prop_path, prop_label, start, end, errors)
                if prop.get("stationary") is False and len(prop_path) < 2:
                    errors.append(f"{prop_label}: moving prop requires at least two path waypoints")

        camera = shot.get("camera")
        if not isinstance(camera, dict):
            errors.append(f"{shot_id}: camera must be an object")
        else:
            mode = camera.get("mode")
            if mode not in ALLOWED_CAMERA_MODES:
                errors.append(f"{shot_id}: unsupported camera mode {mode!r}")
            stationary = camera.get("stationary")
            camera_path = camera.get("path", [])
            validate_path(camera_path, f"{shot_id}.camera", start, end, errors)
            if mode == "static" and stationary is not True:
                errors.append(f"{shot_id}: static camera must declare stationary=true")
            if mode in SPATIAL_CAMERA_MODES and len(camera_path) < 2:
                errors.append(f"{shot_id}: {mode} camera requires at least two path waypoints")

    sortable.sort(key=lambda item: (item[0], item[1], item[2]))
    prior_end = 0
    for start, end, shot_id, _shot in sortable:
        if start < prior_end:
            errors.append(f"{shot_id}: overlaps the prior shot at frame {start}")
        elif start > prior_end:
            warnings.append(f"timeline gap [{prior_end}, {start}) before {shot_id}")
        prior_end = max(prior_end, end)
    total_frames = round(float(duration) * fps)
    if prior_end < total_frames:
        warnings.append(f"timeline ends at frame {prior_end}; project ends at {total_frames}")

    return errors, warnings


def print_validation(errors: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print(f"VALID: {len(warnings)} warning(s)")


def copy_comparison_asset(output: Path) -> str | None:
    source = Path(__file__).resolve().parent.parent / "assets" / "storyboard-levels-1-4.png"
    if not source.exists():
        return "comparison image is missing from the skill assets"
    destination_dir = output / "assets"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        if sha256(destination) != sha256(source):
            return f"kept existing different asset: {destination}"
        return None
    shutil.copy2(source, destination)
    return None


def export_csv(plan: dict[str, Any], output: Path) -> None:
    project = plan["project"]
    fps = project["fps"]
    rows: list[dict[str, Any]] = []
    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        start = shot["start_frame"]
        end = shot["end_frame"]
        story = shot.get("story", {})
        camera = shot.get("camera", {})
        board = shot.get("board", {})
        rows.append(
            {
                "id": shot.get("id", ""),
                "scene_id": shot.get("scene_id", ""),
                "start_sec": frame_seconds(start, fps),
                "end_sec": frame_seconds(end, fps),
                "duration_sec": frame_seconds(end - start, fps),
                "title": shot.get("title", ""),
                "purpose": story.get("purpose", ""),
                "visible_change": story.get("visible_change", ""),
                "camera_mode": camera.get("mode", ""),
                "roughness_level": board.get(
                    "roughness_level", project.get("default_roughness_level", 2)
                ),
                "status": board.get("status", "planned"),
            }
        )
    fields = [
        "id",
        "scene_id",
        "start_sec",
        "end_sec",
        "duration_sec",
        "title",
        "purpose",
        "visible_change",
        "camera_mode",
        "roughness_level",
        "status",
    ]
    with (output / "shotlist.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_action_timeline(plan: dict[str, Any], output: Path) -> None:
    fps = plan["project"]["fps"]
    fields = [
        "shot_id",
        "character_id",
        "phase",
        "start_frame",
        "end_frame",
        "start_sec",
        "end_sec",
        "pose",
        "action",
        "gaze",
        "speed",
    ]
    rows: list[dict[str, Any]] = []
    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        for character in shot.get("characters", []):
            for phase in character.get("action_phases", []):
                start = phase.get("start_frame", shot.get("start_frame", 0))
                end = phase.get("end_frame", shot.get("end_frame", 0))
                rows.append(
                    {
                        "shot_id": shot.get("id", ""),
                        "character_id": character.get("character_id", ""),
                        "phase": phase.get("name", ""),
                        "start_frame": start,
                        "end_frame": end,
                        "start_sec": frame_seconds(start, fps),
                        "end_sec": frame_seconds(end, fps),
                        "pose": phase.get("pose", ""),
                        "action": phase.get("action", ""),
                        "gaze": phase.get("gaze", ""),
                        "speed": phase.get("speed", ""),
                    }
                )
    with (output / "action_timeline.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_motion_paths(plan: dict[str, Any], output: Path) -> None:
    fps = plan["project"]["fps"]
    fields = [
        "shot_id",
        "owner_type",
        "owner_id",
        "waypoint_index",
        "frame",
        "time_sec",
        "x",
        "y",
        "label",
    ]
    rows: list[dict[str, Any]] = []

    def add_path(shot_id: str, owner_type: str, owner_id: str, path: list[dict[str, Any]]) -> None:
        for waypoint_index, point in enumerate(path):
            frame = point.get("frame", 0)
            rows.append(
                {
                    "shot_id": shot_id,
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "waypoint_index": waypoint_index,
                    "frame": frame,
                    "time_sec": frame_seconds(frame, fps),
                    "x": point.get("x", ""),
                    "y": point.get("y", ""),
                    "label": point.get("label", ""),
                }
            )

    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        shot_id = shot.get("id", "")
        for character in shot.get("characters", []):
            add_path(
                shot_id,
                "character",
                character.get("character_id", ""),
                character.get("path", []),
            )
        for prop in shot.get("props", []):
            add_path(shot_id, "prop", prop.get("prop_id", ""), prop.get("path", []))
        camera = shot.get("camera", {})
        add_path(shot_id, "camera", "camera", camera.get("path", []))

    with (output / "motion_paths.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_path(path: list[dict[str, Any]], fps: int) -> str:
    if not path:
        return "stationary / no screen travel"
    points = []
    for point in path:
        frame = point.get("frame", 0)
        x = point.get("x", "")
        y = point.get("y", "")
        label = point.get("label", "")
        suffix = f" {label}" if label else ""
        points.append(f"{frame_seconds(frame, fps)}s ({x}, {y}){suffix}")
    return " -> ".join(points)


def export_timing_summary(plan: dict[str, Any], output: Path) -> None:
    project = plan["project"]
    fps = project["fps"]
    lines = [
        f"# {project.get('title', 'Storyboard')} - Detailed timing and motion",
        "",
        f"Duration: {project.get('duration_seconds')}s / {fps}fps / {project.get('aspect_ratio')}",
        "",
        "Coordinates use normalized screen space: top-left `(0, 0)`, bottom-right `(1, 1)`.",
        "",
    ]
    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        start = shot["start_frame"]
        end = shot["end_frame"]
        story = shot.get("story", {})
        visual = shot.get("visual", {})
        lines.extend(
            [
                f"## {shot.get('id', '')} - {shot.get('title', '')}",
                "",
                f"Time: `{frame_seconds(start, fps)}-{frame_seconds(end, fps)}s` / frames `[{start}, {end})`",
                "",
                f"Purpose: {story.get('purpose', '')}",
                "",
                f"Visible change: {story.get('visible_change', '')}",
                "",
                f"Framing: {visual.get('shot_size', '')}; {visual.get('angle', '')}; {visual.get('lens', '')}",
                "",
            ]
        )
        for character in shot.get("characters", []):
            character_id = character.get("character_id", "")
            gaze = character.get("gaze", {})
            lines.extend(
                [
                    f"### Character - {character_id}",
                    "",
                    f"- Pose: {character.get('start_pose', '')} -> {character.get('end_pose', '')}",
                    f"- Body facing: {character.get('body_facing_start', '')} -> {character.get('body_facing_end', '')}",
                    f"- Gaze: {gaze.get('start_target', '')} -> {gaze.get('end_target', '')}",
                    f"- ACT path: {format_path(character.get('path', []), fps)}",
                    "",
                    "| Time | Phase | Pose | Action | Gaze | Speed |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for phase in character.get("action_phases", []):
                phase_values = [
                    f"{frame_seconds(phase.get('start_frame', start), fps)}-{frame_seconds(phase.get('end_frame', end), fps)}s",
                    phase.get("name", ""),
                    phase.get("pose", ""),
                    phase.get("action", ""),
                    phase.get("gaze", ""),
                    phase.get("speed", ""),
                ]
                safe_values = [str(value).replace("|", "/").replace("\n", " ") for value in phase_values]
                lines.append("| " + " | ".join(safe_values) + " |")
            lines.append("")

        camera = shot.get("camera", {})
        lines.extend(
            [
                "### Camera",
                "",
                f"- Mode: {camera.get('mode', '')}",
                f"- Framing: {camera.get('start_framing', '')} -> {camera.get('end_framing', '')}",
                f"- Target: {camera.get('target', '')}",
                f"- CAM path: {format_path(camera.get('path', []), fps)}",
                "",
            ]
        )
        for prop in shot.get("props", []):
            lines.extend(
                [
                    f"### Prop - {prop.get('prop_id', '')}",
                    "",
                    f"- PROP path: {format_path(prop.get('path', []), fps)}",
                    "",
                ]
            )
        continuity = shot.get("continuity", [])
        constraints = shot.get("constraints", [])
        if continuity:
            lines.append("Continuity: " + "; ".join(str(value) for value in continuity))
            lines.append("")
        if constraints:
            lines.append("Constraints: " + "; ".join(str(value) for value in constraints))
            lines.append("")
    (output / "timing_summary.md").write_text("\n".join(lines), encoding="utf-8")


def export_readme(plan: dict[str, Any], output: Path) -> None:
    project = plan["project"]
    fps = project["fps"]
    lines = [
        f"# {project.get('title', 'Storyboard')}",
        "",
        "![Storyboard roughness levels](assets/storyboard-levels-1-4.png)",
        "",
        "## Project",
        "",
        f"- Duration: {project.get('duration_seconds')} seconds",
        f"- FPS: {fps}",
        f"- Aspect ratio: {project.get('aspect_ratio')}",
        f"- Default roughness level: {project.get('default_roughness_level')}",
        f"- Timing mode: {project.get('timing_mode')}",
        "",
        "## Shot list",
        "",
        "| Shot | Time | Title | Visible change | Camera | Level | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        start = shot["start_frame"]
        end = shot["end_frame"]
        story = shot.get("story", {})
        camera = shot.get("camera", {})
        board = shot.get("board", {})
        values = [
            shot.get("id", ""),
            f"{frame_seconds(start, fps)}-{frame_seconds(end, fps)}s",
            shot.get("title", ""),
            story.get("visible_change", ""),
            camera.get("mode", ""),
            str(board.get("roughness_level", project.get("default_roughness_level", 2))),
            board.get("status", "planned"),
        ]
        safe_values = [str(value).replace("|", "/").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(safe_values) + " |")
    if not plan.get("shots"):
        lines.append("| - | - | No shots planned yet | - | - | - | - |")
    board_entries = []
    for shot in sorted(plan.get("shots", []), key=lambda value: value.get("start_frame", 0)):
        board = shot.get("board", {})
        board_path = board.get("image")
        if board_path:
            board_entries.append(
                (shot.get("id", ""), shot.get("title", ""), "Storyboard", board_path)
            )
        concept_path = board.get("concept_image")
        if concept_path:
            board_entries.append(
                (shot.get("id", ""), shot.get("title", ""), "Concept still", concept_path)
            )
    if board_entries:
        lines.extend(["", "## Boards", ""])
        for shot_id, title, asset_type, board_path in board_entries:
            alt = f"{shot_id} {title} - {asset_type}".strip()
            lines.extend([f"### {alt}", "", f"![{alt}]({board_path})", ""])
    lines.extend(
        [
            "",
            "## Motion legend",
            "",
            "- `ACT`: character travel",
            "- `CAM`: camera motion",
            "- `GAZE`: eye-line or head turn",
            "- `PROP`: independent prop motion",
            "- `ROT`: body or object rotation",
            "- `X`: stop or final mark",
            "",
            "Detailed human-readable motion plan: `timing_summary.md`.",
            "Timing and blocking source of truth: `storyboard_plan.json`.",
            "Derived action phases: `action_timeline.csv`.",
            "Derived actor, prop, and camera waypoints: `motion_paths.csv`.",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def command_init(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "storyboard_plan.json"
    if plan_path.exists():
        print(f"ERROR: refusing to overwrite existing plan: {plan_path}", file=sys.stderr)
        return 2
    plan = new_plan(args)
    write_json(plan_path, plan)
    warning = copy_comparison_asset(output)
    export_csv(plan, output)
    export_action_timeline(plan, output)
    export_motion_paths(plan, output)
    export_timing_summary(plan, output)
    export_readme(plan, output)
    if warning:
        print(f"WARNING: {warning}")
    print(f"CREATED: {plan_path}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).resolve()
    try:
        plan = load_json(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate_plan(plan)
    print_validation(errors, warnings)
    return 1 if errors else 0


def command_export(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).resolve()
    output = Path(args.output).resolve()
    try:
        plan = load_json(plan_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate_plan(plan)
    print_validation(errors, warnings)
    if errors:
        print("ERROR: export stopped because the plan is invalid", file=sys.stderr)
        return 1
    output.mkdir(parents=True, exist_ok=True)
    warning = copy_comparison_asset(output)
    export_csv(plan, output)
    export_action_timeline(plan, output)
    export_motion_paths(plan, output)
    export_timing_summary(plan, output)
    export_readme(plan, output)
    if warning:
        print(f"WARNING: {warning}")
    print(f"EXPORTED: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a new storyboard project")
    init_parser.add_argument("--output", required=True)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--duration", required=True, type=float)
    init_parser.add_argument("--fps", type=int, default=24)
    init_parser.add_argument("--aspect-ratio", default="16:9")
    init_parser.add_argument("--level", type=int, choices=(1, 2, 3, 4), default=2)
    init_parser.add_argument(
        "--timing-mode",
        choices=("user_locked", "ai_proposed_user_approved"),
        default="ai_proposed_user_approved",
    )
    init_parser.set_defaults(handler=command_init)

    validate_parser = subparsers.add_parser("validate", help="validate a storyboard plan")
    validate_parser.add_argument("--plan", required=True)
    validate_parser.set_defaults(handler=command_validate)

    export_parser = subparsers.add_parser("export", help="export README and CSV views")
    export_parser.add_argument("--plan", required=True)
    export_parser.add_argument("--output", required=True)
    export_parser.set_defaults(handler=command_export)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
