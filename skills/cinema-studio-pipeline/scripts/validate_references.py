#!/usr/bin/env python3
"""Validate active shot references, role compatibility, and state isolation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from _cinema_common import (
    canonical_relpath,
    discover_approval_paths,
    discover_asset_paths,
    discover_shot_paths,
    find_bound_approvals,
    issue,
    read_json,
    read_project,
)


ROLE_KINDS = {
    "IDENTITY": {"CHARACTER", "CREATURE"},
    "WARDROBE": {"CHARACTER", "CREATURE", "WARDROBE"},
    "STATE": {"CHARACTER", "CREATURE", "WARDROBE", "PROP", "VEHICLE"},
    "LOCATION_GEOMETRY": {"LOCATION"},
    "MATERIAL_LIGHT": {"LOCATION", "STYLE_REFERENCE"},
    "PROP_FUNCTION": {"PROP", "VEHICLE"},
    "MOTION": {"MOTION_REFERENCE", "CHARACTER", "CREATURE"},
    "AUDIO": {"AUDIO", "VOICE"},
    "STYLE": {"STYLE_REFERENCE"},
}
SINGLETON_ROLES = {
    "LOCATION_GEOMETRY",
    "MATERIAL_LIGHT",
    "STYLE",
}
FORMAT_REQUIREMENTS = {
    "MOTION_REFERENCE": {"MOTION"},
    "MUSIC_LIPSYNC": {"AUDIO"},
}


def _load_assets(project_root: Path, project: dict, errors: list[dict]) -> dict[str, dict]:
    assets: dict[str, dict] = {}
    approvals: list[tuple[dict, Path]] = []
    for approval_path in discover_approval_paths(project_root, project):
        try:
            approval = read_json(approval_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(approval_path, project_root)))
            continue
        if isinstance(approval, dict):
            approvals.append((approval, approval_path))
    for path in discover_asset_paths(project_root, project):
        try:
            asset = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(path, project_root)))
            continue
        if not isinstance(asset, dict) or not isinstance(asset.get("asset_id"), str):
            errors.append(issue("INVALID_ASSET", "Per-record asset file must contain asset_id", path=canonical_relpath(path, project_root)))
            continue
        files = asset.get("files") if isinstance(asset.get("files"), dict) else {}
        master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
        try:
            target = (project_root / master["path"]).resolve() if isinstance(master.get("path"), str) else None
            if target is not None:
                target.relative_to(project_root.resolve())
        except (KeyError, ValueError):
            target = None
        matches = (
            find_bound_approvals(
                project_root,
                approvals,
                project_id=str(project.get("project_id", "")),
                subject_type="ASSET",
                subject_id=asset["asset_id"],
                gate="ASSET_LOCK",
                target_path=target,
                statuses={"USER_APPROVED", "REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"},
                require_current=True,
            )
            if target is not None
            else []
        )
        annotated = dict(asset)
        if len(matches) == 1:
            annotated["_central_review_status"] = matches[0][0].get("review_status")
        elif len(matches) > 1:
            errors.append(issue("E_UNAPPROVED_INPUT", f"Asset has multiple current central decisions: {asset['asset_id']}", path=canonical_relpath(path, project_root)))
        assets[asset["asset_id"]] = annotated
    return assets


def _selected_shots(project_root: Path, project: dict, shot_paths: list[str | Path] | None) -> list[Path]:
    if shot_paths is not None:
        selected: set[Path] = set()
        for raw_path in shot_paths:
            candidate = Path(raw_path).expanduser()
            resolved = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
            try:
                resolved.relative_to(project_root.resolve())
            except ValueError as exc:
                raise ValueError(f"Selected shot path escapes project root: {raw_path}") from exc
            selected.add(resolved)
        return sorted(selected)
    return discover_shot_paths(project_root, project)


def _validate_shot(
    shot: dict,
    path: Path,
    project_root: Path,
    assets: dict[str, dict],
    errors: list[dict],
    warnings: list[dict],
) -> None:
    location = canonical_relpath(path, project_root)
    references = shot.get("active_assets", [])
    if not isinstance(references, list):
        errors.append(issue("E_REFERENCE_ROLE_CONFLICT", "active_assets must be an array", path=location))
        return

    roles: defaultdict[str, list[str]] = defaultdict(list)
    referenced_ids: set[str] = set()
    explicit_mutex: set[tuple[str, str]] = set()

    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"active_assets[{index}] must be an object", path=location))
            continue
        asset_id = reference.get("asset_id")
        role = reference.get("role")
        if not isinstance(asset_id, str) or asset_id not in assets:
            errors.append(issue("E_UNAPPROVED_INPUT", f"Unknown active asset: {asset_id!r}", path=location, index=index))
            continue
        asset = assets[asset_id]
        referenced_ids.add(asset_id)
        status = asset.get("_central_review_status")
        if status in {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"} or asset.get("excluded") is True:
            errors.append(issue("E_EXCLUDED_INPUT", f"Excluded asset cannot be active: {asset_id}", path=location))
        elif status != "USER_APPROVED":
            errors.append(issue("E_UNAPPROVED_INPUT", f"Asset is not approved: {asset_id} ({status})", path=location))

        if not isinstance(role, str) or role not in ROLE_KINDS:
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Unknown reference role for {asset_id}: {role!r}", path=location))
            continue
        roles[role].append(asset_id)
        kind = asset.get("kind")
        allowed_roles = asset.get("allowed_roles")
        if isinstance(allowed_roles, list) and role not in allowed_roles:
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Asset {asset_id} does not allow role {role}", path=location))
        elif kind not in ROLE_KINDS[role]:
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Asset kind {kind!r} cannot fill role {role}", path=location, asset_id=asset_id))

        state = asset.get("state") if isinstance(asset.get("state"), dict) else {}
        if reference.get("state_label") and reference.get("state_label") != state.get("label"):
            errors.append(issue("E_MUTEX_REFERENCE", f"Reference state_label does not match asset visible state: {asset_id}", path=location))
        mutex_values = state.get("mutually_exclusive_with", [])
        if isinstance(mutex_values, list):
            for other in mutex_values:
                if isinstance(other, str):
                    explicit_mutex.add(tuple(sorted((asset_id, other))))

    for role, asset_ids in roles.items():
        if role in SINGLETON_ROLES and len(asset_ids) > 1:
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Role {role} is assigned more than once", path=location, asset_ids=asset_ids))
    for left, right in sorted(explicit_mutex):
        if left in referenced_ids and right in referenced_ids:
            errors.append(issue("E_MUTEX_REFERENCE", f"Mutually exclusive assets are both active: {left}, {right}", path=location))

    audio = shot.get("audio")
    dialogue = audio.get("dialogue") if isinstance(audio, dict) else []
    if isinstance(dialogue, list) and dialogue:
        for index, line in enumerate(dialogue):
            speaker_asset_id = line.get("speaker_asset_id") if isinstance(line, dict) else None
            voice_asset_id = line.get("voice_asset_id") if isinstance(line, dict) else None
            active_speaker_ids = set(roles.get("IDENTITY", [])) | set(roles.get("STATE", []))
            speaker = assets.get(speaker_asset_id, {}) if isinstance(speaker_asset_id, str) else {}
            voice = assets.get(voice_asset_id, {}) if isinstance(voice_asset_id, str) else {}
            if (
                not isinstance(speaker_asset_id, str)
                or speaker_asset_id not in active_speaker_ids
                or speaker.get("kind") != "CHARACTER"
            ):
                errors.append(
                    issue(
                        "E_REFERENCE_ROLE_CONFLICT",
                        f"Dialogue line {index} speaker must be an active CHARACTER in IDENTITY or STATE",
                        path=location,
                        index=index,
                    )
                )
            if (
                not isinstance(voice_asset_id, str)
                or voice_asset_id not in roles.get("AUDIO", [])
                or voice.get("kind") != "VOICE"
            ):
                errors.append(
                    issue(
                        "E_REFERENCE_ROLE_CONFLICT",
                        f"Dialogue line {index} must bind one approved VOICE asset active in the AUDIO role",
                        path=location,
                        index=index,
                    )
                )
                continue
            speaker_lineage = speaker.get("lineage") if isinstance(speaker.get("lineage"), dict) else {}
            voice_lineage = voice.get("lineage") if isinstance(voice.get("lineage"), dict) else {}
            speaker_owner = speaker_lineage.get("immutable_master_asset_id") or speaker_asset_id
            voice_owner = voice_lineage.get("parent_asset_id")
            if not isinstance(voice_owner, str) or voice_owner != speaker_owner:
                errors.append(
                    issue(
                        "E_REFERENCE_ROLE_CONFLICT",
                        f"Dialogue line {index} VOICE must belong to the same character as its speaker",
                        path=location,
                        index=index,
                        speaker_asset_id=speaker_asset_id,
                        voice_asset_id=voice_asset_id,
                    )
                )

    format_mode = shot.get("format_mode", "REFERENCE_TEXT_NATIVE")
    for required_role in FORMAT_REQUIREMENTS.get(format_mode, set()):
        if required_role not in roles:
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"{format_mode} requires role {required_role}", path=location))
    if format_mode == "BOUNDARY_FRAME":
        boundary = shot.get("boundary_frames")
        if not isinstance(boundary, dict) or not any(
            boundary.get(key) for key in ("start_asset_id", "end_asset_id")
        ):
            errors.append(issue("E_REFERENCE_ROLE_CONFLICT", "BOUNDARY_FRAME requires a start or end boundary asset", path=location))
        elif isinstance(boundary, dict):
            for key in ("start_asset_id", "end_asset_id"):
                asset_id = boundary.get(key)
                if not asset_id:
                    continue
                asset = assets.get(asset_id)
                if asset is None:
                    errors.append(issue("E_UNAPPROVED_INPUT", f"Unknown boundary asset: {asset_id}", path=location))
                elif asset.get("_central_review_status") in {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}:
                    errors.append(issue("E_EXCLUDED_INPUT", f"Excluded boundary asset cannot be used: {asset_id}", path=location))
                elif asset.get("_central_review_status") != "USER_APPROVED":
                    errors.append(issue("E_UNAPPROVED_INPUT", f"Boundary asset is not USER_APPROVED: {asset_id}", path=location))

    if len(references) > 15:
        warnings.append(issue("REFERENCE_BUDGET", "More than 15 active references may exceed provider limits", path=location, count=len(references)))


def validate_references(
    project_root: str | Path, *, shot_paths: list[str | Path] | None = None
) -> dict:
    """Return reference validation results without mutating any project file."""

    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    warnings: list[dict] = []
    checked: list[str] = []
    if not root.is_dir():
        return {"ok": False, "errors": [issue("PROJECT_NOT_FOUND", f"Project directory not found: {root}")], "warnings": [], "checked_files": []}
    try:
        project = read_project(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "errors": [issue("PROJECT_FILE_MISSING", str(exc))], "warnings": [], "checked_files": []}
    try:
        assets = _load_assets(root, project, errors)
        selected = _selected_shots(root, project, shot_paths)
    except ValueError as exc:
        return {
            "ok": False,
            "errors": errors + [issue("PATH_ESCAPE", str(exc))],
            "warnings": warnings,
            "checked_files": checked,
        }
    for path in selected:
        checked.append(canonical_relpath(path, root))
        try:
            shot = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(path, root)))
            continue
        if not isinstance(shot, dict):
            errors.append(issue("INVALID_SHOT", "Shot file must contain an object", path=canonical_relpath(path, root)))
            continue
        _validate_shot(shot, path, root, assets, errors, warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked_files": checked}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--shot", action="append", type=Path, dest="shot_paths")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_references(args.project_root, shot_paths=args.shot_paths)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["ok"] else "FAIL")
        for item in result["errors"]:
            print(f"ERROR {item['code']} [{item.get('path', '-') }]: {item['message']}")
        for item in result["warnings"]:
            print(f"WARN {item['code']} [{item.get('path', '-') }]: {item['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
