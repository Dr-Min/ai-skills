#!/usr/bin/env python3
"""Validate a Cinema Studio v2 project and its cross-record approval state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import stat
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from _cinema_common import (
    REVIEW_STATUSES,
    authority_path,
    canonical_relpath,
    discover_approval_paths,
    discover_asset_paths,
    discover_shot_paths,
    discover_take_paths,
    find_bound_approvals,
    issue,
    offline_remote_package_error,
    project_path as resolve_project_path,
    read_json,
    record_id,
    safe_project_path,
    sha256_file,
)
from decision_receipts import verify_decision_receipt
from inspect_media import inspect_media


STAGE_ORDER = (
    "STORY",
    "STORYBOARD",
    "LOOKDEV",
    "ASSET_LOCK",
    "SHOT_STILL",
    "RAW_VIDEO",
    "SOURCE_LIBRARY",
    "EDIT",
    "FINISH",
)
SCHEMA_IDS = {
    name: f"cinema-studio-pipeline/{name}@2.0.0"
    for name in (
        "project",
        "asset",
        "shot",
        "storyboard",
        "take",
        "approval",
        "source-library",
        "timeline",
        "delivery",
    )
}
GATE_SUBJECT_TYPES = {
    "STORY": "STORY",
    "STORYBOARD": "STORYBOARD",
    "LOOKDEV": "LOOKDEV",
    "ASSET_LOCK": "ASSET",
    "SHOT_STILL": "SHOT_STILL",
    "RAW_VIDEO": "TAKE",
    "SOURCE_LIBRARY": "SOURCE_LIBRARY",
    "EDIT": "TIMELINE",
    "FINISH": "DELIVERY",
}
OFFLINE_VERIFICATION = {
    "verification_scope": "OFFLINE_RECORD_CONSISTENCY",
    "remote_truth_verified": False,
}
REVIEW_READY_APPROVAL_STATUSES = frozenset({"USER_REVIEW_REQUIRED", "USER_APPROVED"})
TERMINAL_APPROVAL_STATUSES = frozenset(
    {"USER_APPROVED", "REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
)


def _safe_record_path(
    project_root: Path,
    raw_path: object,
    record_path: Path,
    errors: list[dict],
) -> Path | None:
    if not isinstance(raw_path, str):
        return None
    try:
        return safe_project_path(project_root, raw_path)
    except ValueError as exc:
        errors.append(
            issue(
                "PATH_ESCAPE",
                str(exc),
                path=canonical_relpath(record_path, project_root),
            )
        )
        return None


def _load(path: Path, root: Path, errors: list[dict], checked: set[str]) -> Any:
    relative = canonical_relpath(path, root)
    checked.add(relative)
    try:
        return read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(issue("INVALID_JSON", str(exc), path=relative))
        return None


def _collect_records(project_root: Path, project: dict, errors: list[dict], checked: set[str]) -> dict:
    records: dict[str, list[tuple[dict, Path]]] = {
        "assets": [],
        "shots": [],
        "takes": [],
        "approvals": [],
        "sources": [],
        "source_manifests": [],
        "storyboards": [],
        "timelines": [],
        "deliveries": [],
    }

    def object_record(payload: Any, path: Path, label: str) -> dict | None:
        if payload is None:
            return None
        if not isinstance(payload, dict):
            errors.append(
                issue(
                    "INVALID_RECORD",
                    f"{label} JSON root must contain an object",
                    path=canonical_relpath(path, project_root),
                )
            )
            return None
        return payload

    for path in discover_asset_paths(project_root, project):
        payload = object_record(_load(path, project_root, errors, checked), path, "Asset")
        if payload is not None:
            records["assets"].append((payload, path))
    for path in discover_shot_paths(project_root, project):
        payload = object_record(_load(path, project_root, errors, checked), path, "Shot")
        if payload is not None:
            records["shots"].append((payload, path))
    for path in discover_take_paths(project_root, project):
        payload = object_record(_load(path, project_root, errors, checked), path, "Take")
        if payload is not None:
            records["takes"].append((payload, path))
    for path in discover_approval_paths(project_root, project):
        payload = object_record(_load(path, project_root, errors, checked), path, "Approval")
        if payload is not None:
            if not isinstance(payload.get("approval_id"), str) or not payload.get("approval_id"):
                errors.append(
                    issue(
                        "INVALID_RECORD",
                        "Approval record requires a non-empty approval_id",
                        path=canonical_relpath(path, project_root),
                    )
                )
            records["approvals"].append((payload, path))

    source_manifest = authority_path(
        project_root, project, "source_manifest", "06_source_library/source_manifest.json"
    )
    if source_manifest.exists():
        payload = object_record(_load(source_manifest, project_root, errors, checked), source_manifest, "Source manifest")
        if payload is not None:
            records["source_manifests"].append((payload, source_manifest))
            sources = payload.get("sources", payload.get("approved_sources", []))
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        records["sources"].append((source, source_manifest))
                    else:
                        errors.append(issue("INVALID_RECORD", "Source manifest entries must be objects", path=canonical_relpath(source_manifest, project_root)))

    timeline_path = authority_path(project_root, project, "timeline", "07_edit/timeline.json")
    if timeline_path.exists():
        payload = object_record(_load(timeline_path, project_root, errors, checked), timeline_path, "Timeline")
        if payload is not None:
            records["timelines"].append((payload, timeline_path))
    timeline_root = project_root / "07_edit"
    if timeline_root.is_dir():
        current_timeline = timeline_path.resolve()
        seed_timeline = timeline_root / "timeline.json"
        if seed_timeline.is_file() and seed_timeline.resolve() != current_timeline:
            payload = object_record(
                _load(seed_timeline, project_root, errors, checked),
                seed_timeline,
                "Timeline",
            )
            if payload is not None:
                records["timelines"].append((payload, seed_timeline.resolve()))
        for candidate in sorted((timeline_root / "records").rglob("timeline.json")):
            relative_candidate = candidate.relative_to(timeline_root).as_posix()
            if re.fullmatch(
                r"records/[a-z][a-z0-9]*(?:_[a-z0-9]+)*/v[0-9]{3,}/timeline\.json",
                relative_candidate,
            ) is None:
                continue
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(project_root)
            except (OSError, ValueError):
                errors.append(issue("PATH_ESCAPE", "Unsafe timeline record path", path=canonical_relpath(candidate, project_root)))
                continue
            if resolved == current_timeline:
                continue
            payload = object_record(_load(resolved, project_root, errors, checked), resolved, "Timeline")
            if payload is not None:
                records["timelines"].append((payload, resolved))
    delivery_path = authority_path(project_root, project, "delivery_record", "08_delivery/delivery.json")
    if delivery_path.exists():
        payload = object_record(_load(delivery_path, project_root, errors, checked), delivery_path, "Delivery")
        if payload is not None:
            records["deliveries"].append((payload, delivery_path))

    # Delivery records are immutable authorities. Validate historical records as
    # well as the current project pointer, while never following links outside
    # the project root.
    delivery_root = project_root / "08_delivery"
    if delivery_root.is_dir():
        current_delivery = delivery_path.resolve() if delivery_path.exists() else delivery_path.resolve()
        seed_delivery = delivery_root / "delivery.json"
        if seed_delivery.is_file() and seed_delivery.resolve() != current_delivery:
            payload = object_record(
                _load(seed_delivery, project_root, errors, checked),
                seed_delivery,
                "Delivery",
            )
            if payload is not None:
                records["deliveries"].append((payload, seed_delivery.resolve()))
        for candidate in sorted((delivery_root / "records").rglob("delivery.json")):
            relative_candidate = candidate.relative_to(delivery_root).as_posix()
            if re.fullmatch(
                r"records/[a-z][a-z0-9]*(?:_[a-z0-9]+)*/v[0-9]{3,}/delivery\.json",
                relative_candidate,
            ) is None:
                continue
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(project_root)
            except (OSError, ValueError):
                errors.append(issue("PATH_ESCAPE", "Unsafe delivery record path", path=canonical_relpath(candidate, project_root)))
                continue
            if resolved == current_delivery:
                continue
            payload = object_record(_load(resolved, project_root, errors, checked), resolved, "Delivery")
            if payload is not None:
                records["deliveries"].append((payload, resolved))
    storyboard_path = authority_path(project_root, project, "storyboard", "02_storyboard/storyboard.json")
    if storyboard_path.exists():
        payload = object_record(_load(storyboard_path, project_root, errors, checked), storyboard_path, "Storyboard")
        if payload is not None:
            records["storyboards"].append((payload, storyboard_path))
    return records


def _schema_targets(
    project: dict | None,
    project_path: Path,
    records: dict[str, list[tuple[dict, Path]]],
) -> Iterable[tuple[str, dict, Path]]:
    if isinstance(project, dict):
        yield "project", project, project_path
    singular = {
        "assets": "asset",
        "shots": "shot",
        "takes": "take",
        "approvals": "approval",
        "timelines": "timeline",
        "source_manifests": "source-library",
        "storyboards": "storyboard",
        "deliveries": "delivery",
    }
    for group, schema_name in singular.items():
        for record, path in records[group]:
            yield schema_name, record, path


def _external_schema_ref(schema: object) -> str | None:
    if isinstance(schema, dict):
        for keyword in ("$ref", "$dynamicRef", "$recursiveRef"):
            reference = schema.get(keyword)
            if isinstance(reference, str) and not reference.startswith("#"):
                return f"{keyword}={reference}"
        for value in schema.values():
            found = _external_schema_ref(value)
            if found is not None:
                return found
    elif isinstance(schema, list):
        for value in schema:
            found = _external_schema_ref(value)
            if found is not None:
                return found
    return None


def _required_format_checker(jsonschema: Any) -> Any:
    """Return a checker that does not silently omit optional format extras."""

    checker = jsonschema.FormatChecker()

    def valid_datetime(value: object) -> bool:
        if not isinstance(value, str):
            return True  # The schema's type keyword governs non-string values.
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            value,
        ) is None:
            return False
        try:
            parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
            return parsed.tzinfo is not None
        except ValueError:
            return False

    def valid_uri(value: object) -> bool:
        if not isinstance(value, str):
            return True
        if not value or any(character.isspace() for character in value):
            return False
        parsed = urlsplit(value)
        return bool(parsed.scheme and (parsed.netloc or parsed.scheme in {"urn", "mailto"}))

    checker.checks("date-time")(valid_datetime)
    checker.checks("uri")(valid_uri)
    return checker


def _validate_schema_snapshot_trust(
    project_root: Path,
    project: dict,
    schema_dir: Path,
    errors: list[dict],
    checked: set[str],
) -> bool:
    """Bind a project snapshot to the installed, trusted schema manifest."""

    starting_error_count = len(errors)
    trusted_dir = Path(__file__).resolve().parents[1] / "schemas"
    trusted_manifest_path = trusted_dir / "schema-manifest.json"
    try:
        project_manifest_path = authority_path(
            project_root,
            project,
            "schema_manifest",
            "00_schemas/schema-manifest.json",
        )
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        return False
    checked.add(canonical_relpath(project_manifest_path, project_root))
    if not trusted_manifest_path.is_file():
        errors.append(issue("TRUSTED_SCHEMA_MANIFEST_MISSING", "Installed trusted schema manifest is missing"))
        return False
    if not project_manifest_path.is_file():
        errors.append(
            issue(
                "SCHEMA_MANIFEST_MISSING",
                "Project schema snapshot manifest is missing",
                path=canonical_relpath(project_manifest_path, project_root),
            )
        )
        return False
    try:
        trusted = read_json(trusted_manifest_path)
        project_manifest = read_json(project_manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(issue("INVALID_SCHEMA_MANIFEST", str(exc)))
        return False
    if not isinstance(trusted, dict) or not isinstance(project_manifest, dict):
        errors.append(issue("INVALID_SCHEMA_MANIFEST", "Schema manifests must contain objects"))
        return False
    if sha256_file(project_manifest_path) != sha256_file(trusted_manifest_path):
        errors.append(
            issue(
                "SCHEMA_MANIFEST_MISMATCH",
                "Project schema manifest differs from the installed trusted manifest",
                path=canonical_relpath(project_manifest_path, project_root),
            )
        )
    entries = trusted.get("schemas") if isinstance(trusted.get("schemas"), list) else []
    expected_files = {f"{name}.schema.json" for name in SCHEMA_IDS}
    manifest_files = {
        item.get("filename")
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("filename"), str)
    }
    if manifest_files != expected_files:
        errors.append(issue("INVALID_SCHEMA_MANIFEST", "Trusted schema manifest file set is incomplete"))
    for item in entries:
        if not isinstance(item, dict):
            errors.append(issue("INVALID_SCHEMA_MANIFEST", "Trusted schema manifest contains an invalid entry"))
            continue
        filename, expected = item.get("filename"), item.get("sha256")
        if not isinstance(filename, str) or not isinstance(expected, str):
            errors.append(issue("INVALID_SCHEMA_MANIFEST", "Trusted schema manifest entry lacks filename/SHA-256"))
            continue
        canonical = trusted_dir / filename
        snapshot = schema_dir / filename
        if not canonical.is_file() or sha256_file(canonical).casefold() != expected.casefold():
            errors.append(issue("TRUSTED_SCHEMA_HASH_MISMATCH", f"Installed schema does not match its trusted manifest: {filename}"))
        if not snapshot.is_file():
            errors.append(
                issue(
                    "SCHEMA_MISSING",
                    f"Required project snapshot schema is missing: {filename}",
                    path=str(schema_dir.resolve()),
                )
            )
            continue
        checked.add(canonical_relpath(snapshot, project_root))
        if sha256_file(snapshot).casefold() != expected.casefold():
            errors.append(
                issue(
                    "SCHEMA_SNAPSHOT_HASH_MISMATCH",
                    f"Project schema snapshot does not match the trusted manifest: {filename}",
                    path=canonical_relpath(snapshot, project_root),
                )
            )
    return len(errors) == starting_error_count


def _validate_schemas(
    project_root: Path,
    schema_dir: Path,
    targets: Iterable[tuple[str, dict, Path]],
    errors: list[dict],
    warnings: list[dict],
) -> None:
    targets = list(targets)
    for schema_name, instance, source_path in targets:
        expected_schema_id = SCHEMA_IDS[schema_name]
        actual_schema_id = instance.get("schema_id") if isinstance(instance, dict) else None
        if actual_schema_id is None:
            errors.append(issue("SCHEMA_ID_MISSING", f"schema_id is required and must be {expected_schema_id}", path=canonical_relpath(source_path, project_root)))
        elif actual_schema_id != expected_schema_id:
            errors.append(issue("SCHEMA_ID_MISMATCH", f"schema_id must be {expected_schema_id}", path=canonical_relpath(source_path, project_root), actual=actual_schema_id))
    if not schema_dir.exists():
        errors.append(
            issue(
                "SCHEMA_DIR_MISSING",
                f"Schema directory does not exist: {schema_dir}",
            )
        )
        return
    missing_schema_names = {
        schema_name
        for schema_name in SCHEMA_IDS
        if not (schema_dir / f"{schema_name}.schema.json").is_file()
    }
    for schema_name in sorted(missing_schema_names):
        errors.append(
            issue(
                "SCHEMA_MISSING",
                f"Required project snapshot schema is missing: {schema_name}.schema.json",
                path=str(schema_dir.resolve()),
            )
        )
    try:
        import jsonschema
    except ImportError:
        errors.append(
            issue(
                "SCHEMA_ENGINE_MISSING",
                "Install 'jsonschema' to perform required v2 schema validation",
            )
        )
        return

    cache: dict[str, tuple[dict, Path]] = {}
    for schema_name, instance, source_path in targets:
        schema_path = schema_dir / f"{schema_name}.schema.json"
        schema_ref = instance.get("$schema") if isinstance(instance, dict) else None
        if isinstance(schema_ref, str):
            resolved_ref = (source_path.parent / schema_ref).resolve()
            if resolved_ref != schema_path.resolve() or not resolved_ref.is_file():
                errors.append(
                    issue(
                        "SCHEMA_REF_INVALID",
                        f"$schema must resolve to the project schema snapshot {schema_path.name}",
                        path=canonical_relpath(source_path, project_root),
                        resolved=str(resolved_ref),
                    )
                )
        if not schema_path.exists():
            continue
        if schema_name not in cache:
            try:
                schema = read_json(schema_path)
                cache[schema_name] = (schema, schema_path)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(
                    issue("INVALID_SCHEMA", str(exc), path=str(schema_path.resolve()))
                )
                continue
        schema, schema_path = cache[schema_name]
        try:
            external_ref = _external_schema_ref(schema)
            if external_ref is not None:
                errors.append(
                    issue(
                        "INVALID_SCHEMA",
                        f"External schema references are forbidden in project snapshots: {external_ref}",
                        path=str(schema_path.resolve()),
                    )
                )
                continue
            validator_class = jsonschema.validators.validator_for(schema)
            validator_class.check_schema(schema)
            validator = validator_class(schema, format_checker=_required_format_checker(jsonschema))
            for validation_error in sorted(
                validator.iter_errors(instance), key=lambda err: list(err.absolute_path)
            ):
                location = "/".join(map(str, validation_error.absolute_path)) or "$"
                errors.append(
                    issue(
                        "SCHEMA_ERROR",
                        f"{location}: {validation_error.message}",
                        path=canonical_relpath(source_path, project_root),
                        schema=canonical_relpath(schema_path, schema_dir),
                    )
                )
        except Exception as exc:  # Schema/ref failures are reported, never hidden.
            errors.append(
                issue(
                    "SCHEMA_ENGINE_ERROR",
                    str(exc),
                    path=canonical_relpath(source_path, project_root),
                    schema=str(schema_path.resolve()),
                )
            )


def _check_unique_ids(
    project_root: Path, records: dict[str, list[tuple[dict, Path]]], errors: list[dict]
) -> None:
    for group, items in records.items():
        seen: dict[str, Path] = {}
        for record, path in items:
            identifier = record_id(record)
            if identifier is None:
                continue
            if group in {"timelines", "deliveries"} and isinstance(record.get("version"), int):
                identifier = f"{identifier}@v{record['version']:03d}"
            if identifier in seen:
                errors.append(
                    issue(
                        "DUPLICATE_ID",
                        f"Duplicate {group[:-1]} id: {identifier}",
                        path=canonical_relpath(path, project_root),
                        first_path=canonical_relpath(seen[identifier], project_root),
                    )
                )
            else:
                seen[identifier] = path


def _check_statuses(
    project_root: Path,
    project: dict | None,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    status_records: list[tuple[dict, Path]] = []
    if isinstance(project, dict):
        status_records.append((project, project_root / "project.json"))
    for items in records.values():
        status_records.extend(items)
    for record, path in status_records:
        status = record.get("review_status")
        if status is not None and status not in REVIEW_STATUSES:
            errors.append(
                issue(
                    "INVALID_STATUS",
                    f"Unknown review_status: {status!r}",
                    path=canonical_relpath(path, project_root),
                )
            )
    if not isinstance(project, dict):
        return
    stage_statuses = project.get("stage_gates")
    if not isinstance(stage_statuses, dict):
        return
    first_blocker: str | None = None
    for stage in STAGE_ORDER:
        status = stage_statuses.get(stage)
        if status is None:
            continue
        if first_blocker is None and status != "USER_APPROVED":
            first_blocker = stage
        elif first_blocker is not None and status == "USER_APPROVED":
            errors.append(
                issue(
                    "STAGE_ORDER",
                    f"{stage} cannot be USER_APPROVED before {first_blocker}",
                    path="project.json",
                )
            )


def _check_project_ids(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    expected = project.get("project_id")
    if not isinstance(expected, str):
        return
    for group, items in records.items():
        for record, path in items:
            if "project_id" in record and record.get("project_id") != expected:
                errors.append(
                    issue(
                        "PROJECT_ID_MISMATCH",
                        f"{group[:-1]} project_id must equal project.json project_id {expected}",
                        path=canonical_relpath(path, project_root),
                        actual=record.get("project_id"),
                    )
                )


def _bound_content_approvals(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    *,
    subject_type: str,
    subject_id: object,
    gate: str,
    target_path: Path,
    statuses: set[str] | frozenset[str],
    require_current: bool = True,
) -> list[tuple[dict, Path]]:
    if not isinstance(project.get("project_id"), str) or not isinstance(subject_id, str):
        return []
    return find_bound_approvals(
        project_root,
        records["approvals"],
        project_id=project["project_id"],
        subject_type=subject_type,
        subject_id=subject_id,
        gate=gate,
        target_path=target_path,
        statuses=statuses,
        require_current=require_current,
    )


def _production_subject_path(
    project_root: Path, group: str, record: dict, record_path: Path
) -> Path | None:
    if group == "shots":
        return record_path.resolve()
    if group == "assets":
        files = record.get("files") if isinstance(record.get("files"), dict) else {}
        master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
        raw_path = master.get("path")
    elif group == "takes":
        raw_path = record.get("output_file")
    else:
        return record_path.resolve()
    if not isinstance(raw_path, str):
        return None
    try:
        return safe_project_path(project_root, raw_path)
    except ValueError:
        return None


def _check_active_stage_approvals(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    gates = project.get("stage_gates") if isinstance(project.get("stage_gates"), dict) else {}
    approved_gates = [gate for gate in STAGE_ORDER if gates.get(gate) == "USER_APPROVED"]
    if not approved_gates:
        return
    expected_project = project.get("project_id")
    active = project.get("active_approval_ids") if isinstance(project.get("active_approval_ids"), list) else []
    active_ids = [value for value in active if isinstance(value, str)]
    approvals = {
        approval.get("approval_id"): (approval, path)
        for approval, path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    valid_active = {
        approval_id: item
        for approval_id in active_ids
        if (item := approvals.get(approval_id)) is not None
        and item[0].get("project_id") == expected_project
        and item[0].get("review_status") == "USER_APPROVED"
        and not item[0].get("superseded_by_approval_id")
    }
    collection_gates = {
        "ASSET_LOCK": ("assets", "asset_id", "ASSET"),
        "SHOT_STILL": ("shots", "shot_id", "SHOT_STILL"),
        "RAW_VIDEO": ("takes", "take_id", "TAKE"),
    }
    terminal_statuses = {"USER_APPROVED", "REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
    excluded_terminal_statuses = {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
    storyboard = records["storyboards"][0][0] if records["storyboards"] else {}

    def planned_record_ids(gate: str) -> set[str] | None:
        if not isinstance(storyboard, dict):
            return None
        if gate == "ASSET_LOCK":
            raw_plan, id_key = storyboard.get("asset_plan"), "asset_id"
        elif gate == "SHOT_STILL":
            raw_plan, id_key = storyboard.get("shot_plan"), "shot_id"
        else:
            return None
        if not isinstance(raw_plan, list) or not raw_plan:
            return None
        return {
            item[id_key]
            for item in raw_plan
            if isinstance(item, dict) and isinstance(item.get(id_key), str)
        }

    def structured_authority(gate: str) -> tuple[dict, Path] | None:
        mapping = {
            "STORYBOARD": ("storyboards", "storyboard", "02_storyboard/storyboard.json"),
            "SOURCE_LIBRARY": ("source_manifests", "source_manifest", "06_source_library/source_manifest.json"),
            "EDIT": ("timelines", "timeline", "07_edit/timeline.json"),
            "FINISH": ("deliveries", "delivery_record", "08_delivery/delivery.json"),
        }
        group, authority_key, default = mapping[gate]
        target = authority_path(project_root, project, authority_key, default).resolve()
        matches = [
            (record, path.resolve())
            for record, path in records[group]
            if path.resolve() == target
        ]
        return matches[0] if len(matches) == 1 else None

    def singular_authority(gate: str) -> tuple[str | None, str | None]:
        if gate == "STORY":
            target = authority_path(project_root, project, "story_contract", "01_story/STORY_CONTRACT.md")
            return "story-contract", sha256_file(target) if target.is_file() else None
        if gate == "LOOKDEV":
            target = authority_path(project_root, project, "visual_bible", "03_lookdev/VISUAL_BIBLE.md")
            return "visual-bible", sha256_file(target) if target.is_file() else None
        id_keys = {
            "STORYBOARD": "storyboard_id",
            "SOURCE_LIBRARY": "library_id",
            "EDIT": "timeline_id",
            "FINISH": "delivery_id",
        }
        item = structured_authority(gate)
        if item is None:
            return None, None
        record, path = item
        return record.get(id_keys[gate]), sha256_file(path) if path.is_file() else None

    for gate in approved_gates:
        active_for_gate = {
            approval_id: item
            for approval_id, item in valid_active.items()
            if item[0].get("gate") == gate
            and item[0].get("subject_type") == GATE_SUBJECT_TYPES[gate]
        }
        if gate not in collection_gates:
            if len(active_for_gate) != 1:
                errors.append(
                    issue(
                        "E_STAGE_PREREQ",
                        f"USER_APPROVED singular gate {gate} requires exactly one active same-project {GATE_SUBJECT_TYPES[gate]} approval",
                        path="project.json",
                    )
                )
            else:
                approval, approval_path = next(iter(active_for_gate.values()))
                try:
                    expected_id, expected_hash = singular_authority(gate)
                except ValueError as exc:
                    errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
                    expected_id, expected_hash = None, None
                if (
                    expected_id is None
                    or expected_hash is None
                    or approval.get("subject_id") != expected_id
                    or approval.get("subject_sha256") != expected_hash
                ):
                    errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Active singular approval is not bound to the current {gate} authority", path=canonical_relpath(approval_path, project_root)))
                structured = {
                    "STORYBOARD": "storyboards",
                    "SOURCE_LIBRARY": "source_manifests",
                    "EDIT": "timelines",
                    "FINISH": "deliveries",
                }.get(gate)
                if structured and records[structured]:
                    authority_item = structured_authority(gate)
                    if authority_item is None:
                        errors.append(
                            issue(
                                "E_STAGE_PREREQ",
                                f"Current {gate} authority pointer does not select exactly one discovered record",
                                path="project.json",
                            )
                        )
                        continue
            continue

        group, id_key, subject_type = collection_gates[gate]
        production_records = records[group]
        if not production_records:
            errors.append(issue("E_STAGE_PREREQ", f"Collection gate {gate} cannot be USER_APPROVED without production records", path="project.json"))
            continue
        central_decisions: dict[str, tuple[dict, Path] | None] = {}
        for record, record_path in production_records:
            identifier = record.get(id_key)
            if not isinstance(identifier, str):
                continue
            target_path = _production_subject_path(project_root, group, record, record_path)
            matches = (
                find_bound_approvals(
                    project_root,
                    records["approvals"],
                    project_id=str(expected_project),
                    subject_type=subject_type,
                    subject_id=identifier,
                    gate=gate,
                    target_path=target_path,
                    statuses=terminal_statuses,
                    require_current=True,
                )
                if target_path is not None
                else []
            )
            if len(matches) > 1:
                errors.append(
                    issue(
                        "E_STAGE_PREREQ",
                        f"Current production record has multiple terminal central decisions: {identifier}",
                        path=canonical_relpath(record_path, project_root),
                    )
                )
            central_decisions[identifier] = matches[0] if len(matches) == 1 else None
        unresolved = [
            record.get(id_key)
            for record, _ in production_records
            if central_decisions.get(record.get(id_key)) is None
        ]
        if unresolved:
            errors.append(issue("E_STAGE_PREREQ", f"Collection gate {gate} has unresolved production records", path="project.json", record_ids=unresolved))
        approved_records = [
            item
            for item in production_records
            if central_decisions.get(item[0].get(id_key)) is not None
            and central_decisions[item[0].get(id_key)][0].get("review_status") == "USER_APPROVED"
        ]
        plan_ids = planned_record_ids(gate)
        if plan_ids is not None:
            approved_record_ids = {
                record.get(id_key)
                for record, _ in approved_records
                if isinstance(record.get(id_key), str)
            }
            missing_plan_ids = sorted(plan_ids - approved_record_ids)
            for missing_id in missing_plan_ids:
                noun = "asset" if gate == "ASSET_LOCK" else "shot"
                errors.append(
                    issue(
                        "MISSING_PLANNED_ASSET" if gate == "ASSET_LOCK" else "MISSING_PLANNED_SHOT",
                        f"Collection gate {gate} is missing USER_APPROVED planned {noun}: {missing_id}",
                        path="project.json",
                    )
                )
            for record, record_path in production_records:
                identifier = record.get(id_key)
                decision = central_decisions.get(identifier)
                decision_status = decision[0].get("review_status") if decision is not None else None
                if identifier in plan_ids or decision_status in excluded_terminal_statuses:
                    continue
                noun = "asset" if gate == "ASSET_LOCK" else "shot"
                errors.append(
                    issue(
                        "E_STAGE_PREREQ",
                        f"Unplanned production {noun} must be explicitly rejected, superseded, or excluded: {identifier}",
                        path=canonical_relpath(record_path, project_root),
                    )
                )
            if gate == "ASSET_LOCK":
                plan_by_id = {
                    item.get("asset_id"): item
                    for item in storyboard.get("asset_plan", [])
                    if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
                }
                for record, record_path in approved_records:
                    identifier = record.get("asset_id")
                    planned = plan_by_id.get(identifier)
                    if planned is None:
                        continue
                    state = record.get("state") if isinstance(record.get("state"), dict) else {}
                    if (
                        record.get("kind") != planned.get("kind")
                        or state.get("label") != planned.get("state_label")
                    ):
                        errors.append(
                            issue(
                                "ASSET_PLAN_MISMATCH",
                                f"USER_APPROVED asset {identifier} kind/state does not match storyboard asset_plan",
                                path=canonical_relpath(record_path, project_root),
                            )
                        )
        if not approved_records:
            errors.append(issue("E_STAGE_PREREQ", f"Collection gate {gate} requires at least one USER_APPROVED production record", path="project.json"))
            continue
        if gate == "RAW_VIDEO" and isinstance(storyboard, dict):
            coverage_minimums: dict[str, int] = {}
            for planned_shot in storyboard.get("shot_plan", []) if isinstance(storyboard.get("shot_plan"), list) else []:
                if not isinstance(planned_shot, dict):
                    continue
                for requirement in planned_shot.get("coverage_requirements", []) if isinstance(planned_shot.get("coverage_requirements"), list) else []:
                    if not isinstance(requirement, dict):
                        continue
                    coverage_id, minimum = requirement.get("coverage_id"), requirement.get("minimum_approved_takes")
                    if isinstance(coverage_id, str) and isinstance(minimum, int) and minimum >= 1:
                        coverage_minimums[coverage_id] = minimum
            approved_counts = {coverage_id: 0 for coverage_id in coverage_minimums}
            for take, _ in approved_records:
                for coverage_id in take.get("coverage_requirement_ids", []) if isinstance(take.get("coverage_requirement_ids"), list) else []:
                    if coverage_id in approved_counts:
                        approved_counts[coverage_id] += 1
            for coverage_id, minimum in coverage_minimums.items():
                if approved_counts[coverage_id] < minimum:
                    errors.append(
                        issue(
                            "COVERAGE_MINIMUM_NOT_MET",
                            f"Coverage requirement {coverage_id} requires {minimum} USER_APPROVED takes; found {approved_counts[coverage_id]}",
                            path="project.json",
                        )
                    )
        required_ids: set[str] = set()
        for record, record_path in approved_records:
            identifier = record.get(id_key)
            decision = central_decisions.get(identifier)
            approval_id = decision[0].get("approval_id") if decision is not None else None
            if not isinstance(approval_id, str):
                errors.append(issue("E_STAGE_PREREQ", f"USER_APPROVED {group[:-1]} lacks approval_id: {identifier}", path=canonical_relpath(record_path, project_root)))
                continue
            required_ids.add(approval_id)
            approval_item = active_for_gate.get(approval_id)
            if approval_item is None:
                errors.append(issue("E_STAGE_PREREQ", f"Collection gate {gate} is missing the active approval for {identifier}", path="project.json"))
                continue
            approval, approval_path = approval_item
            if approval.get("subject_type") != subject_type or approval.get("subject_id") != identifier:
                errors.append(issue("E_UNAPPROVED_INPUT", f"Active approval does not target current {group[:-1]} {identifier}", path=canonical_relpath(approval_path, project_root)))
                continue
            if group == "assets":
                lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
                expected_hash = lineage.get("output_sha256")
            elif group == "takes":
                expected_hash = record.get("output_sha256")
            else:
                expected_hash = sha256_file(record_path)
            if not isinstance(expected_hash, str) or approval.get("subject_sha256") != expected_hash:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Active collection approval hash is stale for {identifier}", path=canonical_relpath(approval_path, project_root)))
        if set(active_for_gate) != required_ids:
            errors.append(issue("E_STAGE_PREREQ", f"Collection gate {gate} active approvals must exactly cover its USER_APPROVED records", path="project.json"))
    approved_gate_set = set(approved_gates)
    for approval_id in active_ids:
        approval_item = valid_active.get(approval_id)
        if approval_item is None or approval_item[0].get("gate") not in approved_gate_set:
            errors.append(issue("E_STAGE_PREREQ", f"Active approval is unknown, cross-project, or belongs to a non-approved gate: {approval_id}", path="project.json"))
    if len(active_ids) != len(set(active_ids)):
        errors.append(issue("E_STAGE_PREREQ", "Active approval IDs must be unique", path="project.json"))

def _check_references(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    project_id = project.get("project_id")
    assets_by_id = {
        asset.get("asset_id"): asset
        for asset, _ in records["assets"]
        if isinstance(asset.get("asset_id"), str)
    }
    asset_decisions: dict[str, str | None] = {}
    for asset, asset_path in records["assets"]:
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str):
            continue
        target = _production_subject_path(project_root, "assets", asset, asset_path)
        matches = (
            _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="ASSET",
                subject_id=asset_id,
                gate="ASSET_LOCK",
                target_path=target,
                statuses=TERMINAL_APPROVAL_STATUSES,
            )
            if target is not None
            else []
        )
        asset_decisions[asset_id] = matches[0][0].get("review_status") if len(matches) == 1 else None
    assets = set(assets_by_id)
    shots = {record_id(shot) for shot, _ in records["shots"] if record_id(shot)}
    takes = {record_id(take) for take, _ in records["takes"] if record_id(take)}
    sources = {
        record_id(source) for source, _ in records["sources"] if record_id(source)
    }

    storyboard_item = records["storyboards"][0] if records["storyboards"] else None
    storyboard = storyboard_item[0] if storyboard_item is not None else None
    storyboard_location = canonical_relpath(storyboard_item[1], project_root) if storyboard_item is not None else "02_storyboard/storyboard.json"
    storyboard_approved = bool(
        _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="STORYBOARD",
            subject_id=storyboard.get("storyboard_id") if isinstance(storyboard, dict) else None,
            gate="STORYBOARD",
            target_path=storyboard_item[1] if storyboard_item is not None else project_root / "02_storyboard" / "storyboard.json",
            statuses={"USER_APPROVED"},
        )
    )
    panel_scene: dict[str, str | None] = {}
    panels: list[dict] = []
    if isinstance(storyboard, dict):
        scenes = storyboard.get("scenes")
        if isinstance(scenes, list):
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                scene_id = scene.get("scene_id") if isinstance(scene.get("scene_id"), str) else None
                for panel in scene.get("panels", []) if isinstance(scene.get("panels"), list) else []:
                    if isinstance(panel, dict):
                        panels.append(panel)
                        panel_id = panel.get("panel_id")
                        if isinstance(panel_id, str):
                            if panel_id in panel_scene:
                                errors.append(issue("DUPLICATE_PANEL_ID", f"Duplicate storyboard panel ID: {panel_id}", path=storyboard_location))
                            panel_scene[panel_id] = scene_id
        elif isinstance(storyboard.get("panels"), list):
            for panel in storyboard["panels"]:
                if isinstance(panel, dict):
                    panels.append(panel)
                    panel_id = panel.get("panel_id")
                    if isinstance(panel_id, str):
                        if panel_id in panel_scene:
                            errors.append(issue("DUPLICATE_PANEL_ID", f"Duplicate storyboard panel ID: {panel_id}", path=storyboard_location))
                        panel_scene[panel_id] = storyboard.get("scene_id") if isinstance(storyboard.get("scene_id"), str) else None
    storyboard_panels = set(panel_scene)
    asset_plan_ids: set[str] = set()
    coverage_requirements: dict[str, dict] = {}
    shot_plan: dict[str, dict] = {}

    def planned_coverage_ids(item: dict) -> list[str]:
        raw = item.get("coverage_requirements", item.get("coverage_requirement_ids", []))
        identifiers: list[str] = []
        for value in raw if isinstance(raw, list) else []:
            if isinstance(value, dict) and isinstance(value.get("coverage_id"), str):
                identifiers.append(value["coverage_id"])
            elif isinstance(value, str):
                identifiers.append(value)
        return identifiers

    if isinstance(storyboard, dict):
        for item in storyboard.get("asset_plan", []) if isinstance(storyboard.get("asset_plan"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("asset_id"), str):
                continue
            asset_id = item["asset_id"]
            if asset_id in asset_plan_ids:
                errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard asset_plan ID: {asset_id}", path=storyboard_location))
            asset_plan_ids.add(asset_id)
        for item in storyboard.get("shot_plan", []) if isinstance(storyboard.get("shot_plan"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("shot_id"), str):
                continue
            shot_id = item["shot_id"]
            if shot_id in shot_plan:
                errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard shot_plan ID: {shot_id}", path=storyboard_location))
            shot_plan[shot_id] = item
            scene_id = item.get("scene_id")
            for panel_id in item.get("storyboard_panel_ids", []) if isinstance(item.get("storyboard_panel_ids"), list) else []:
                if panel_id not in storyboard_panels or (panel_scene.get(panel_id) is not None and panel_scene.get(panel_id) != scene_id):
                    errors.append(issue("UNKNOWN_PANEL", f"Planned shot references an unknown or cross-scene panel: {panel_id}", path=storyboard_location))
            for asset_id in item.get("required_asset_ids", []) if isinstance(item.get("required_asset_ids"), list) else []:
                if asset_id not in asset_plan_ids:
                    errors.append(issue("UNKNOWN_PLANNED_ASSET", f"Planned shot references asset outside asset_plan: {asset_id}", path=storyboard_location))
            raw_coverage = item.get("coverage_requirements", item.get("coverage_requirement_ids", []))
            for coverage_item in raw_coverage if isinstance(raw_coverage, list) else []:
                if isinstance(coverage_item, dict):
                    coverage_id = coverage_item.get("coverage_id")
                    if not isinstance(coverage_id, str):
                        continue
                    if coverage_id in coverage_requirements:
                        errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard coverage requirement: {coverage_id}", path=storyboard_location))
                    coverage_requirements[coverage_id] = coverage_item
                elif isinstance(coverage_item, str) and coverage_item not in coverage_requirements:
                    errors.append(issue("UNKNOWN_COVERAGE_REQUIREMENT", f"Planned shot references unknown coverage requirement: {coverage_item}", path=storyboard_location))

    for shot, path in records["shots"]:
        location = canonical_relpath(path, project_root)
        shot_review_ready = bool(
            _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="SHOT_STILL",
                subject_id=shot.get("shot_id"),
                gate="SHOT_STILL",
                target_path=path,
                statuses=REVIEW_READY_APPROVAL_STATUSES,
            )
        )
        references = shot.get("active_assets", [])
        active_roles: dict[tuple[str, str], int] = {}
        if isinstance(references, list):
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                asset_id = reference.get("asset_id")
                role = reference.get("role")
                if isinstance(asset_id, str) and isinstance(role, str):
                    key = (asset_id, role)
                    active_roles[key] = active_roles.get(key, 0) + 1
                if asset_id and asset_id not in assets:
                    errors.append(
                        issue(
                            "UNKNOWN_ASSET",
                            f"Shot references unknown asset: {asset_id}",
                            path=location,
                        )
                    )
                elif isinstance(asset_id, str):
                    asset = assets_by_id[asset_id]
                    if asset.get("project_id") != project_id:
                        errors.append(issue("PROJECT_ID_MISMATCH", f"Active asset belongs to another project: {asset_id}", path=location))
                    decision_status = asset_decisions.get(asset_id)
                    if decision_status in {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}:
                        errors.append(issue("E_EXCLUDED_INPUT", f"Excluded asset cannot be active: {asset_id}", path=location))
                    elif decision_status != "USER_APPROVED":
                        errors.append(issue("E_UNAPPROVED_INPUT", f"Active asset is not USER_APPROVED: {asset_id}", path=location))

        def require_structural_asset(asset_id: object, role: str, label: str) -> None:
            if not isinstance(asset_id, str):
                return
            asset = assets_by_id.get(asset_id)
            if asset is None:
                errors.append(issue("UNKNOWN_ASSET", f"{label} references unknown asset: {asset_id}", path=location))
                return
            if asset.get("project_id") != project_id:
                errors.append(issue("PROJECT_ID_MISMATCH", f"{label} asset belongs to another project: {asset_id}", path=location))
            decision_status = asset_decisions.get(asset_id)
            if decision_status in {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}:
                errors.append(issue("E_EXCLUDED_INPUT", f"{label} asset is excluded: {asset_id}", path=location))
            elif decision_status != "USER_APPROVED":
                errors.append(issue("E_UNAPPROVED_INPUT", f"{label} asset is not USER_APPROVED: {asset_id}", path=location))
            if active_roles.get((asset_id, role), 0) != 1:
                errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"{label} asset must appear exactly once in active_assets with role {role}: {asset_id}", path=location))

        motion_ids = shot.get("motion_reference_asset_ids")
        for asset_id in motion_ids if isinstance(motion_ids, list) else []:
            require_structural_asset(asset_id, "MOTION", "Motion reference")
        spatial = shot.get("spatial") if isinstance(shot.get("spatial"), dict) else {}
        require_structural_asset(spatial.get("location_asset_id"), "LOCATION_GEOMETRY", "Spatial location")
        continuity = shot.get("continuity") if isinstance(shot.get("continuity"), dict) else {}
        state_ids = continuity.get("state_asset_ids")
        for asset_id in state_ids if isinstance(state_ids, list) else []:
            require_structural_asset(asset_id, "STATE", "Continuity state")

        panel_ids = shot.get("storyboard_panel_ids")
        for panel_id in panel_ids if isinstance(panel_ids, list) else []:
            if panel_id not in storyboard_panels:
                errors.append(issue("UNKNOWN_PANEL", f"Shot references a panel outside the current storyboard: {panel_id}", path=location))
        if (
            isinstance(panel_ids, list)
            and panel_ids
            and shot_review_ready
            and not storyboard_approved
        ):
            errors.append(issue("E_UNAPPROVED_INPUT", "Review-ready shot requires the current USER_APPROVED storyboard", path=location))
        coverage_ids = shot.get("coverage_requirement_ids")
        for coverage_id in coverage_ids if isinstance(coverage_ids, list) else []:
            if coverage_id not in coverage_requirements:
                errors.append(issue("UNKNOWN_COVERAGE_REQUIREMENT", f"Shot references unknown storyboard coverage requirement: {coverage_id}", path=location))
        planned = shot_plan.get(shot.get("shot_id"))
        if planned is not None:
            if shot.get("scene_id") != planned.get("scene_id"):
                errors.append(issue("ID_PREFIX_MISMATCH", f"Shot scene differs from the approved shot plan: {shot.get('shot_id')}", path=location))
            planned_panels = planned.get("storyboard_panel_ids") if isinstance(planned.get("storyboard_panel_ids"), list) else []
            if isinstance(panel_ids, list) and panel_ids != planned_panels:
                errors.append(issue("E_STAGE_PREREQ", f"Shot storyboard panels differ from the current shot plan: {shot.get('shot_id')}", path=location))
            planned_coverage = planned_coverage_ids(planned)
            if isinstance(coverage_ids, list) and set(coverage_ids) != set(planned_coverage):
                errors.append(issue("E_STAGE_PREREQ", f"Shot coverage requirements differ from the current shot plan: {shot.get('shot_id')}", path=location))
        boundary = shot.get("boundary_frames", {})
        if isinstance(boundary, dict):
            for field in ("start_asset_id", "end_asset_id"):
                asset_id = boundary.get(field)
                if asset_id and asset_id not in assets:
                    errors.append(
                        issue(
                            "UNKNOWN_ASSET",
                            f"{field} references unknown asset: {asset_id}",
                            path=location,
                        )
                    )
                elif asset_id:
                    asset = assets_by_id[asset_id]
                    if asset_decisions.get(asset_id) != "USER_APPROVED":
                        errors.append(issue("E_UNAPPROVED_INPUT", f"Boundary asset is not USER_APPROVED: {asset_id}", path=location))

    for take, path in records["takes"]:
        shot_id = take.get("shot_id")
        if shot_id and shot_id not in shots:
            errors.append(
                issue(
                    "UNKNOWN_SHOT",
                    f"Take references unknown shot: {shot_id}",
                    path=canonical_relpath(path, project_root),
                )
            )
        parent_take = take.get("parent_take_id")
        if parent_take and parent_take not in takes:
            errors.append(
                issue(
                    "UNKNOWN_PARENT_TAKE",
                    f"Take references unknown parent take: {parent_take}",
                    path=canonical_relpath(path, project_root),
                )
            )
        take_coverage = take.get("coverage_requirement_ids")
        shot_record = next((shot for shot, _ in records["shots"] if shot.get("shot_id") == shot_id), None)
        shot_coverage = shot_record.get("coverage_requirement_ids") if isinstance(shot_record, dict) and isinstance(shot_record.get("coverage_requirement_ids"), list) else []
        for coverage_id in take_coverage if isinstance(take_coverage, list) else []:
            if coverage_id not in coverage_requirements:
                errors.append(issue("UNKNOWN_COVERAGE_REQUIREMENT", f"Take references unknown storyboard coverage requirement: {coverage_id}", path=canonical_relpath(path, project_root)))
            elif coverage_id not in shot_coverage:
                errors.append(issue("E_STAGE_PREREQ", f"Take coverage is not required by its shot plan: {coverage_id}", path=canonical_relpath(path, project_root)))

def _asset_authority(
    project_root: Path,
    asset: dict,
    asset_path: Path,
    errors: list[dict],
) -> tuple[Path | None, str | None]:
    files = asset.get("files") if isinstance(asset.get("files"), dict) else {}
    master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
    lineage = asset.get("lineage") if isinstance(asset.get("lineage"), dict) else {}
    return (
        _safe_record_path(project_root, master.get("path"), asset_path, errors),
        lineage.get("output_sha256") or master.get("sha256"),
    )


def _check_shot_dependency_snapshots(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    storyboard_item = records["storyboards"][0] if records["storyboards"] else None
    storyboard = storyboard_item[0] if storyboard_item is not None else {}
    storyboard_path = storyboard_item[1].resolve() if storyboard_item is not None else None
    shot_plan = {
        item.get("shot_id"): item
        for item in storyboard.get("shot_plan", []) if isinstance(storyboard, dict) and isinstance(storyboard.get("shot_plan"), list)
        if isinstance(item, dict) and isinstance(item.get("shot_id"), str)
    }
    approvals = {
        approval.get("approval_id"): (approval, approval_path.resolve())
        for approval, approval_path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    assets = {
        asset.get("asset_id"): (asset, asset_path)
        for asset, asset_path in records["assets"]
        if isinstance(asset.get("asset_id"), str)
    }

    try:
        story_path = authority_path(project_root, project, "story_contract", "01_story/STORY_CONTRACT.md")
        lookdev_path = authority_path(project_root, project, "visual_bible", "03_lookdev/VISUAL_BIBLE.md")
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        return

    story_hash = sha256_file(story_path) if story_path.is_file() else None
    story_matches = _bound_content_approvals(
        project_root,
        project,
        records,
        subject_type="STORY",
        subject_id="story-contract",
        gate="STORY",
        target_path=story_path,
        statuses={"USER_APPROVED"},
    )
    story_approval = story_matches[0] if len(story_matches) == 1 else None
    board_hash = sha256_file(storyboard_path) if storyboard_path is not None and storyboard_path.is_file() else None
    board_matches = (
        _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="STORYBOARD",
            subject_id=storyboard.get("storyboard_id"),
            gate="STORYBOARD",
            target_path=storyboard_path,
            statuses={"USER_APPROVED"},
        )
        if storyboard_path is not None
        else []
    )
    board_approval = board_matches[0] if len(board_matches) == 1 else None
    lookdev_hash = sha256_file(lookdev_path) if lookdev_path.is_file() else None
    lookdev_matches = _bound_content_approvals(
        project_root,
        project,
        records,
        subject_type="LOOKDEV",
        subject_id="visual-bible",
        gate="LOOKDEV",
        target_path=lookdev_path,
        statuses={"USER_APPROVED"},
    )
    lookdev_approval = lookdev_matches[0] if len(lookdev_matches) == 1 else None

    def binding_matches(
        binding: object,
        *,
        subject_type: str,
        subject_id: str,
        authority: Path | None,
        digest: str | None,
        approval_item: tuple[dict, Path] | None,
    ) -> bool:
        if not isinstance(binding, dict) or authority is None or digest is None or approval_item is None:
            return False
        approval, approval_path = approval_item
        authority_value = _safe_record_path(project_root, binding.get("authority_path"), approval_path, errors)
        approval_value = _safe_record_path(project_root, binding.get("approval_record_path"), approval_path, errors)
        return (
            binding.get("subject_type") == subject_type
            and binding.get("subject_id") == subject_id
            and binding.get("approval_id") == approval.get("approval_id")
            and binding.get("review_status") == "USER_APPROVED"
            and binding.get("subject_sha256") == digest
            and authority_value == authority.resolve()
            and authority.is_file()
            and sha256_file(authority) == digest
            and approval_value == approval_path
            and approval_path.is_file()
            and approval.get("project_id") == project.get("project_id")
            and approval.get("subject_type") == subject_type
            and approval.get("subject_id") == subject_id
            and approval.get("subject_sha256") == digest
            and approval.get("review_status") == "USER_APPROVED"
            and not approval.get("superseded_by_approval_id")
        )

    for shot, shot_path in records["shots"]:
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="SHOT_STILL",
            subject_id=shot.get("shot_id"),
            gate="SHOT_STILL",
            target_path=shot_path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        if not review_matches:
            continue
        location = canonical_relpath(shot_path, project_root)
        if len(review_matches) > 1:
            errors.append(issue("E_STAGE_PREREQ", "Shot has multiple active review decisions", path=location))
            continue
        planned = shot_plan.get(shot.get("shot_id"))
        snapshot = shot.get("dependency_snapshot") if isinstance(shot.get("dependency_snapshot"), dict) else None
        if planned is None or snapshot is None:
            errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", f"Review-ready shot lacks a current plan/dependency snapshot: {shot.get('shot_id')}", path=location))
            continue
        if snapshot.get("project_id") != project.get("project_id"):
            errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", "Shot dependency snapshot project_id is stale", path=location))
        for label, binding, subject_type, subject_id, authority, digest, approval_item in (
            ("story", snapshot.get("story"), "STORY", "story-contract", story_path, story_hash, story_approval),
            ("storyboard", snapshot.get("storyboard"), "STORYBOARD", storyboard.get("storyboard_id"), storyboard_path, board_hash, board_approval),
            ("lookdev", snapshot.get("lookdev"), "LOOKDEV", "visual-bible", lookdev_path, lookdev_hash, lookdev_approval),
        ):
            if not isinstance(subject_id, str) or not binding_matches(
                binding,
                subject_type=subject_type,
                subject_id=subject_id,
                authority=authority,
                digest=digest,
                approval_item=approval_item,
            ):
                errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", f"Shot dependency snapshot {label} binding is stale", path=location))

        planned_panels = planned.get("storyboard_panel_ids") if isinstance(planned.get("storyboard_panel_ids"), list) else []
        if set(shot.get("storyboard_panel_ids", []) if isinstance(shot.get("storyboard_panel_ids"), list) else []) != set(planned_panels):
            errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", "Shot dependency snapshot panel coverage differs from the current shot plan", path=location))
        planned_coverage = {
            item.get("coverage_id")
            for item in planned.get("coverage_requirements", []) if isinstance(planned.get("coverage_requirements"), list)
            if isinstance(item, dict) and isinstance(item.get("coverage_id"), str)
        }
        actual_coverage = set(shot.get("coverage_requirement_ids", []) if isinstance(shot.get("coverage_requirement_ids"), list) else [])
        if actual_coverage != planned_coverage:
            errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", "Shot dependency snapshot coverage differs from the current shot plan", path=location))

        planned_assets = set(planned.get("required_asset_ids", []) if isinstance(planned.get("required_asset_ids"), list) else [])
        raw_bindings = snapshot.get("required_assets") if isinstance(snapshot.get("required_assets"), list) else []
        binding_assets = {
            binding.get("asset_id")
            for binding in raw_bindings
            if isinstance(binding, dict) and isinstance(binding.get("asset_id"), str)
        }
        if binding_assets != planned_assets:
            errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", "Shot dependency snapshot required asset set differs from the current shot plan", path=location))
        for binding in raw_bindings:
            if not isinstance(binding, dict) or not isinstance(binding.get("asset_id"), str):
                continue
            asset_id = binding["asset_id"]
            asset_item = assets.get(asset_id)
            if asset_item is None:
                errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", f"Shot dependency snapshot required asset is missing: {asset_id}", path=location))
                continue
            asset, asset_path = asset_item
            authority, digest = _asset_authority(project_root, asset, asset_path, errors)
            asset_matches = (
                _bound_content_approvals(
                    project_root,
                    project,
                    records,
                    subject_type="ASSET",
                    subject_id=asset_id,
                    gate="ASSET_LOCK",
                    target_path=authority,
                    statuses={"USER_APPROVED"},
                )
                if authority is not None
                else []
            )
            approval_item = asset_matches[0] if len(asset_matches) == 1 else None
            if (
                not binding_matches(
                    binding,
                    subject_type="ASSET",
                    subject_id=asset_id,
                    authority=authority,
                    digest=digest,
                    approval_item=approval_item,
                )
                or binding.get("asset_id") != asset_id
            ):
                errors.append(issue("DEPENDENCY_SNAPSHOT_STALE", f"Shot dependency snapshot required asset binding is stale: {asset_id}", path=location))


def _check_still_evidence(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    assets = {
        asset.get("asset_id"): (asset, path)
        for asset, path in records["assets"]
        if isinstance(asset.get("asset_id"), str)
    }
    for shot, path in records["shots"]:
        location = canonical_relpath(path, project_root)
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="SHOT_STILL",
            subject_id=shot.get("shot_id"),
            gate="SHOT_STILL",
            target_path=path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        if len(review_matches) > 1:
            errors.append(issue("E_STAGE_PREREQ", "Shot has multiple active review decisions", path=location))
        review_item = review_matches[0] if len(review_matches) == 1 else None
        raw_items = shot.get("still_evidence")
        items = raw_items if isinstance(raw_items, list) else []
        roles: set[str] = set()
        paths: set[Path] = set()
        evidence_pairs: set[tuple[str, str]] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            role, asset_id = item.get("role"), item.get("asset_id")
            raw_path, expected_hash = item.get("path"), item.get("sha256")
            if isinstance(role, str):
                if role in roles:
                    errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Duplicate still evidence role: {role}", path=location))
                roles.add(role)
            resolved = _safe_record_path(project_root, raw_path, path, errors)
            if resolved is not None:
                if resolved in paths:
                    errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Duplicate still evidence path: {raw_path}", path=location))
                paths.add(resolved)
                if (
                    not resolved.is_file()
                    or not isinstance(expected_hash, str)
                    or sha256_file(resolved).casefold() != expected_hash.casefold()
                ):
                    errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Still evidence bytes mismatch: {raw_path}", path=location))
                elif isinstance(raw_path, str):
                    evidence_pairs.add((raw_path.replace("\\", "/"), expected_hash.casefold()))
            asset_item = assets.get(asset_id)
            if asset_item is None:
                if asset_id is None and role == "STILL":
                    continue
                errors.append(issue("UNKNOWN_ASSET", f"Still evidence references unknown asset: {asset_id}", path=location))
                continue
            asset, asset_path = asset_item
            if asset.get("project_id") != project.get("project_id"):
                errors.append(issue("PROJECT_ID_MISMATCH", f"Still evidence asset belongs to another project: {asset_id}", path=location))
            authority_path_value, authority_hash = _asset_authority(project_root, asset, asset_path, errors)
            asset_matches = (
                _bound_content_approvals(
                    project_root,
                    project,
                    records,
                    subject_type="ASSET",
                    subject_id=asset_id,
                    gate="ASSET_LOCK",
                    target_path=authority_path_value,
                    statuses={"USER_APPROVED"},
                )
                if authority_path_value is not None
                else []
            )
            if len(asset_matches) != 1:
                errors.append(issue("E_UNAPPROVED_INPUT", f"Still evidence asset is not USER_APPROVED: {asset_id}", path=location))
            if (
                resolved is None
                or authority_path_value is None
                or resolved != authority_path_value
                or not isinstance(authority_hash, str)
                or not isinstance(expected_hash, str)
                or authority_hash.casefold() != expected_hash.casefold()
            ):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Still evidence is not bound to authoritative asset bytes: {asset_id}", path=location))

        review_ready = review_item is not None
        if review_ready and shot.get("format_mode") == "BOUNDARY_FRAME":
            boundary = shot.get("boundary_frames") if isinstance(shot.get("boundary_frames"), dict) else {}
            expected = [
                ("START", boundary.get("start_asset_id")),
                ("END", boundary.get("end_asset_id")),
            ]
            actual = [(item.get("role"), item.get("asset_id")) for item in items if isinstance(item, dict)]
            if actual != expected:
                errors.append(issue("E_REFERENCE_ROLE_CONFLICT", "Boundary still evidence must be ordered START/END and match boundary_frames asset IDs", path=location))
        elif review_ready:
            actual = [(item.get("role"), item.get("asset_id")) for item in items if isinstance(item, dict)]
            if len(actual) != 1 or actual[0][0] != "STILL":
                errors.append(issue("E_REFERENCE_ROLE_CONFLICT", "Non-boundary review-ready shot requires exactly one STILL evidence item", path=location))

        if review_item is None:
            continue
        approval, approval_path = review_item
        shot_hash = sha256_file(path)
        if (
            approval.get("project_id") != project.get("project_id")
            or approval.get("subject_type") != "SHOT_STILL"
            or approval.get("subject_id") != shot.get("shot_id")
            or approval.get("subject_sha256") != shot_hash
        ):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Shot approval is not bound to current shot authority: {shot.get('shot_id')}", path=canonical_relpath(approval_path, project_root)))
        required = {(location, shot_hash.casefold())} | evidence_pairs
        approval_evidence = {
            (item.get("path", "").replace("\\", "/"), str(item.get("sha256", "")).casefold())
            for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) and isinstance(item, dict)
        }
        if not required.issubset(approval_evidence):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Shot approval evidence must include shot.json and every visible still: {shot.get('shot_id')}", path=canonical_relpath(approval_path, project_root)))


def _frame_or_time_position(value: object) -> tuple[str, float] | None:
    """Parse an explicit zero-based frame index or a non-negative clock position."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        frame_match = re.fullmatch(r"frame\s*(?:=|:)\s*([0-9]+)", text, re.IGNORECASE)
        if frame_match:
            position = float(frame_match.group(1))
            return ("frame", position) if math.isfinite(position) else None
        if ":" not in text:
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text) is None:
                return None
            position = float(text)
            return ("seconds", position) if math.isfinite(position) else None
        parts = text.split(":")
        if len(parts) not in {2, 3}:
            return None
        if any(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", part) is None for part in parts):
            return None
        numbers = [float(part) for part in parts]
        if any(not math.isfinite(part) for part in numbers):
            return None
        if len(parts) == 3:
            hours, minutes, seconds = numbers
            if not hours.is_integer() or not minutes.is_integer() or minutes >= 60 or seconds >= 60:
                return None
            return ("seconds", hours * 3600 + minutes * 60 + seconds)
        minutes, seconds = numbers
        if not minutes.is_integer() or minutes >= 60 or seconds >= 60:
            return None
        return ("seconds", minutes * 60 + seconds)
    except (OverflowError, ValueError):
        return None


def _frame_or_time_value(value: object) -> float | None:
    parsed = _frame_or_time_position(value)
    return parsed[1] if parsed is not None else None


def _iter_qa_evidence(delivery: dict) -> Iterable[dict]:
    qa = delivery.get("qa") if isinstance(delivery.get("qa"), dict) else {}
    for value in qa.values():
        if not isinstance(value, dict):
            continue
        for item in value.get("evidence", []) if isinstance(value.get("evidence"), list) else []:
            if isinstance(item, dict):
                yield item


def _check_deliveries(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    if not records["deliveries"]:
        return
    timelines = [
        (timeline, path.resolve())
        for timeline, path in records["timelines"]
        if isinstance(timeline.get("timeline_id"), str)
    ]
    approvals = {
        approval.get("approval_id"): (approval, path)
        for approval, path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    current_path = authority_path(project_root, project, "delivery_record", "08_delivery/delivery.json")
    current_timeline_path = authority_path(project_root, project, "timeline", "07_edit/timeline.json")
    current_deliveries = [
        (delivery, path.resolve())
        for delivery, path in records["deliveries"]
        if path.resolve() == current_path.resolve()
    ]
    if len(current_deliveries) != 1:
        errors.append(
            issue(
                "DELIVERY_POINTER_INVALID",
                "project.authority_files.delivery_record does not select exactly one discovered delivery record",
                path="project.json",
            )
        )
    elif isinstance(current_deliveries[0][0].get("delivery_id"), str):
        current_delivery = current_deliveries[0][0]
        current_id = current_delivery["delivery_id"]
        versions = [
            item.get("version")
            for item, _ in records["deliveries"]
            if item.get("delivery_id") == current_id and isinstance(item.get("version"), int)
        ]
        if versions and current_delivery.get("version") != max(versions):
            errors.append(
                issue(
                    "DELIVERY_POINTER_INVALID",
                    "project.authority_files.delivery_record must select the newest delivery revision in its chain",
                    path="project.json",
                )
            )
    seen_versions: set[tuple[str, int]] = set()
    for delivery, path in records["deliveries"]:
        location = canonical_relpath(path, project_root)
        is_current_delivery = path.resolve() == current_path.resolve()
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="DELIVERY",
            subject_id=delivery.get("delivery_id"),
            gate="FINISH",
            target_path=path,
            statuses={
                "USER_REVIEW_REQUIRED",
                "USER_APPROVED",
                "REJECTED",
                "SUPERSEDED",
                "EXCLUDED_FROM_INPUTS",
            },
            require_current=is_current_delivery,
        )
        if len(review_matches) > 1:
            errors.append(issue("E_STAGE_PREREQ", "Delivery has multiple applicable central decisions", path=location))
        review_item = review_matches[0] if len(review_matches) == 1 else None
        identity = (delivery.get("delivery_id"), delivery.get("version"))
        if identity in seen_versions:
            errors.append(issue("DUPLICATE_ID", f"Duplicate delivery version: {identity}", path=location))
        seen_versions.add(identity)
        if delivery.get("version") == 1:
            if location != "08_delivery/delivery.json" or delivery.get("supersedes_delivery") is not None:
                errors.append(
                    issue(
                        "DELIVERY_POINTER_INVALID",
                        "Delivery v1 must remain at 08_delivery/delivery.json with no predecessor",
                        path=location,
                    )
                )
        elif isinstance(delivery.get("version"), int) and delivery["version"] >= 2 and isinstance(delivery.get("delivery_id"), str):
            expected_location = f"08_delivery/records/{delivery['delivery_id']}/v{delivery['version']:03d}/delivery.json"
            if location != expected_location:
                errors.append(issue("DELIVERY_POINTER_INVALID", f"Delivery version 2+ must use its immutable versioned path: {expected_location}", path=location))
        source = delivery.get("source_timeline") if isinstance(delivery.get("source_timeline"), dict) else {}
        source_path = _safe_record_path(project_root, source.get("path"), path, errors)
        source_hash = source.get("sha256")
        if source_path is not None and (
            not source_path.is_file()
            or not isinstance(source_hash, str)
            or sha256_file(source_path).casefold() != source_hash.casefold()
        ):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Delivery source timeline bytes mismatch: {delivery.get('delivery_id')}", path=location))
        timeline_matches = [
            (timeline, timeline_path)
            for timeline, timeline_path in timelines
            if timeline.get("timeline_id") == source.get("timeline_id")
            and source_path == timeline_path
            and isinstance(source_hash, str)
            and timeline_path.is_file()
            and sha256_file(timeline_path).casefold() == source_hash.casefold()
        ]
        timeline_item = timeline_matches[0] if len(timeline_matches) == 1 else None
        source_is_declared = any(
            source.get(key) is not None
            for key in ("timeline_id", "path", "sha256")
        )
        source_is_required = review_item is not None
        if timeline_item is not None:
            timeline, timeline_path = timeline_item
            timeline_approvals = _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="TIMELINE",
                subject_id=timeline.get("timeline_id"),
                gate="EDIT",
                target_path=timeline_path,
                statuses={"USER_APPROVED"},
                require_current=is_current_delivery,
            )
            if (
                (is_current_delivery and source_path != current_timeline_path.resolve())
                or (is_current_delivery and timeline_path != current_timeline_path.resolve())
                or (source_is_required and len(timeline_approvals) != 1)
                or timeline.get("lock_status") != "PICTURE_LOCKED"
            ):
                errors.append(issue("E_STAGE_PREREQ", "Reviewed delivery must bind an exact centrally USER_APPROVED PICTURE_LOCKED timeline; the current delivery must bind the current timeline pointer", path=location))
        elif source_is_required or (is_current_delivery and source_is_declared):
            errors.append(issue("E_STAGE_PREREQ", "Delivery references an unknown timeline authority", path=location))
        derivation = delivery.get("derivation") if isinstance(delivery.get("derivation"), dict) else {}
        input_bindings = {
            (item.get("path", "").replace("\\", "/"), str(item.get("sha256", "")).casefold())
            for item in derivation.get("input_hashes", []) if isinstance(derivation.get("input_hashes"), list) and isinstance(item, dict)
        }
        if isinstance(source.get("path"), str) and isinstance(source_hash, str) and (source["path"].replace("\\", "/"), source_hash.casefold()) not in input_bindings:
            errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", "Delivery derivation does not bind its source timeline path and hash", path=location))
        export = delivery.get("export") if isinstance(delivery.get("export"), dict) else {}
        export_path = _safe_record_path(project_root, export.get("path"), path, errors)
        export_hash = export.get("sha256")
        if export_path is not None and (
            not export_path.is_file()
            or not isinstance(export_hash, str)
            or sha256_file(export_path).casefold() != export_hash.casefold()
        ):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Delivery export bytes mismatch: {delivery.get('delivery_id')}", path=location))
        qa_pairs: set[tuple[str, str]] = set()
        for item in _iter_qa_evidence(delivery):
            evidence_path = _safe_record_path(project_root, item.get("path"), path, errors)
            expected = item.get("sha256")
            if evidence_path is None or not evidence_path.is_file() or not isinstance(expected, str) or sha256_file(evidence_path).casefold() != expected.casefold():
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Delivery QA evidence bytes mismatch: {item.get('path')}", path=location))
            elif isinstance(item.get("path"), str):
                qa_pairs.add((item["path"].replace("\\", "/"), expected.casefold()))

        review_ready = review_item is not None
        qa = delivery.get("qa") if isinstance(delivery.get("qa"), dict) else {}
        if review_ready:
            media_integrity = qa.get("media_integrity") if isinstance(qa.get("media_integrity"), dict) else {}
            if media_integrity.get("status") != "PASS":
                errors.append(
                    issue(
                        "DELIVERY_QA_INVALID",
                        "Reviewed delivery requires media_integrity status PASS",
                        path=location,
                    )
                )
            frame_check = qa.get("frame_integrity") if isinstance(qa.get("frame_integrity"), dict) else {}
            frame_evidence = frame_check.get("evidence") if isinstance(frame_check.get("evidence"), list) else []
            frame_roles = [item.get("evidence_role") for item in frame_evidence if isinstance(item, dict)]
            frame_paths = [item.get("path") for item in frame_evidence if isinstance(item, dict)]
            frame_positions = [item.get("frame_or_time") for item in frame_evidence if isinstance(item, dict)]
            role_positions = {
                item.get("evidence_role"): _frame_or_time_position(item.get("frame_or_time"))
                for item in frame_evidence
                if isinstance(item, dict)
            }
            ordered_positions = [role_positions.get(role) for role in ("FIRST_FRAME", "MIDDLE_FRAME", "LAST_FRAME")]
            position_units = {
                value[0] for value in ordered_positions if isinstance(value, tuple)
            }
            numeric_positions = [
                value[1] if isinstance(value, tuple) else None for value in ordered_positions
            ]
            if (
                frame_check.get("status") != "PASS"
                or sorted(frame_roles) != ["FIRST_FRAME", "LAST_FRAME", "MIDDLE_FRAME"]
                or len(frame_paths) != 3
                or len(set(frame_paths)) != 3
                or len(frame_positions) != 3
                or any(not isinstance(value, str) or not value.strip() for value in frame_positions)
                or len(set(frame_positions)) != 3
                or any(value is None for value in numeric_positions)
                or len(position_units) != 1
                or not (
                    isinstance(numeric_positions[0], float)
                    and isinstance(numeric_positions[1], float)
                    and isinstance(numeric_positions[2], float)
                    and numeric_positions[0] < numeric_positions[1] < numeric_positions[2]
                )
            ):
                errors.append(issue("DELIVERY_QA_INVALID", "Delivery frame QA requires distinct FIRST/MIDDLE/LAST paths and positions", path=location))

            media = export.get("media") if isinstance(export.get("media"), dict) else {}
            audio_check = qa.get("audio_sync") if isinstance(qa.get("audio_sync"), dict) else {}
            if media.get("audio_present") is True and (
                audio_check.get("status") != "PASS"
                or not isinstance(audio_check.get("evidence"), list)
                or not audio_check.get("evidence")
            ):
                errors.append(issue("DELIVERY_QA_INVALID", "Delivery with audio requires evidence-backed PASS audio_sync QA", path=location))
            if media.get("audio_present") is False and (
                audio_check.get("status") != "NOT_APPLICABLE"
                or not isinstance(audio_check.get("reason"), str)
                or not audio_check.get("reason", "").strip()
            ):
                errors.append(issue("DELIVERY_QA_INVALID", "Delivery without audio requires reasoned NOT_APPLICABLE audio_sync QA", path=location))
            if export_path is None or not export_path.is_file():
                errors.append(issue("MEDIA_PROOF_UNAVAILABLE", "Delivery export is unavailable for metadata verification", path=location))
            else:
                inspection = inspect_media(export_path)
                if not inspection.get("ok"):
                    errors.append(issue("MEDIA_PROOF_UNAVAILABLE", "ffprobe metadata verification failed for the delivery export", path=location, probe_errors=inspection.get("errors", [])))
                else:
                    video_streams = inspection.get("video_streams") if isinstance(inspection.get("video_streams"), list) else []
                    audio_streams = inspection.get("audio_streams") if isinstance(inspection.get("audio_streams"), list) else []
                    if not video_streams or not isinstance(video_streams[0], dict):
                        errors.append(issue("MEDIA_METADATA_MISMATCH", "Delivery export has no verified video stream", path=location))
                    else:
                        first_video = video_streams[0]
                        if media.get("width") != first_video.get("width") or media.get("height") != first_video.get("height"):
                            errors.append(issue("MEDIA_METADATA_MISMATCH", "Delivery dimensions disagree with ffprobe", path=location))
                        numerator, denominator = media.get("frame_rate_numerator"), media.get("frame_rate_denominator")
                        actual_rate = first_video.get("frame_rate")
                        try:
                            rate_matches = (
                                isinstance(numerator, int)
                                and isinstance(denominator, int)
                                and denominator > 0
                                and isinstance(actual_rate, str)
                                and Fraction(actual_rate) == Fraction(numerator, denominator)
                            )
                        except (ValueError, ZeroDivisionError):
                            rate_matches = False
                        if not rate_matches:
                            errors.append(issue("MEDIA_METADATA_MISMATCH", "Delivery frame rate disagrees with ffprobe", path=location))
                        declared_duration = media.get("duration_seconds")
                        format_data = inspection.get("format") if isinstance(inspection.get("format"), dict) else {}
                        actual_duration = format_data.get("duration_seconds") or first_video.get("duration_seconds")
                        frame_tolerance = (denominator / numerator) if isinstance(numerator, int) and numerator > 0 and isinstance(denominator, int) else 0
                        if (
                            not isinstance(declared_duration, (int, float))
                            or not isinstance(actual_duration, (int, float))
                            or abs(float(declared_duration) - float(actual_duration)) > max(frame_tolerance, 0.001)
                        ):
                            errors.append(issue("MEDIA_METADATA_MISMATCH", "Delivery duration disagrees with ffprobe", path=location))
                        if len(position_units) == 1 and all(
                            isinstance(value, float) for value in numeric_positions
                        ):
                            unit = next(iter(position_units))
                            range_valid = False
                            if unit == "seconds" and isinstance(actual_duration, (int, float)):
                                duration_value = float(actual_duration)
                                range_valid = (
                                    math.isfinite(duration_value)
                                    and numeric_positions[-1] <= duration_value + max(frame_tolerance, 0.001)
                                )
                            elif unit == "frame":
                                actual_frame_count = first_video.get("frame_count")
                                if isinstance(actual_frame_count, int) and not isinstance(actual_frame_count, bool):
                                    range_valid = actual_frame_count > 0 and numeric_positions[-1] < actual_frame_count
                            if not range_valid:
                                errors.append(
                                    issue(
                                        "DELIVERY_QA_INVALID",
                                        "Delivery frame QA positions must stay within the verified media range",
                                        path=location,
                                    )
                                )
                    actual_audio_present = bool(audio_streams)
                    if media.get("audio_present") is not actual_audio_present:
                        errors.append(issue("MEDIA_METADATA_MISMATCH", "delivery.export.media.audio_present disagrees with the actual media streams", path=location))
                    if actual_audio_present and audio_streams:
                        first_audio = audio_streams[0] if isinstance(audio_streams[0], dict) else {}
                        if (
                            media.get("audio_sample_rate_hz") != first_audio.get("sample_rate_hz")
                            or media.get("audio_channels") != first_audio.get("channels")
                        ):
                            errors.append(issue("MEDIA_METADATA_MISMATCH", "Delivery audio stream metadata disagrees with ffprobe", path=location))

        predecessor = delivery.get("supersedes_delivery")
        if isinstance(delivery.get("version"), int) and delivery["version"] >= 2:
            if not isinstance(predecessor, dict):
                errors.append(issue("E_STAGE_PREREQ", "Delivery version 2+ requires an immutable predecessor record", path=location))
            else:
                predecessor_path = _safe_record_path(project_root, predecessor.get("path"), path, errors)
                predecessor_hash = predecessor.get("sha256")
                predecessor_matches = [
                    (candidate, candidate_path.resolve())
                    for candidate, candidate_path in records["deliveries"]
                    if candidate.get("delivery_id") == delivery.get("delivery_id")
                    and candidate.get("version") == delivery["version"] - 1
                ]
                predecessor_item = predecessor_matches[0] if len(predecessor_matches) == 1 else None
                predecessor_record = predecessor_item[0] if predecessor_item is not None else None
                authoritative_predecessor_path = predecessor_item[1] if predecessor_item is not None else None
                predecessor_approval_item = approvals.get(predecessor.get("approval_id"))
                predecessor_approval = predecessor_approval_item[0] if predecessor_approval_item is not None else {}
                predecessor_approval_path = predecessor_approval_item[1] if predecessor_approval_item is not None else None
                predecessor_bound = (
                    isinstance(predecessor_record, dict)
                    and authoritative_predecessor_path is not None
                    and len(
                        _bound_content_approvals(
                            project_root,
                            project,
                            records,
                            subject_type="DELIVERY",
                            subject_id=delivery.get("delivery_id"),
                            gate="FINISH",
                            target_path=authoritative_predecessor_path,
                            statuses={"USER_APPROVED", "REJECTED"},
                            require_current=False,
                        )
                    )
                    == 1
                )
                if (
                    predecessor_path is None
                    or predecessor_path == path.resolve()
                    or not predecessor_path.is_file()
                    or not isinstance(predecessor_hash, str)
                    or sha256_file(predecessor_path).casefold() != predecessor_hash.casefold()
                    or not isinstance(predecessor_record, dict)
                    or predecessor_path != authoritative_predecessor_path
                    or predecessor.get("delivery_id") != delivery.get("delivery_id")
                    or predecessor_record.get("delivery_id") != predecessor.get("delivery_id")
                    or predecessor_record.get("version") != predecessor.get("version")
                    or predecessor.get("version") != delivery.get("version") - 1
                    or predecessor_approval.get("approval_id") != predecessor.get("approval_id")
                    or predecessor_approval.get("review_status") not in {"USER_APPROVED", "REJECTED"}
                    or predecessor_approval_path is None
                    or not predecessor_bound
                ):
                    errors.append(
                        issue(
                            "DELIVERY_PREDECESSOR_INVALID",
                            "Delivery predecessor must be the exact authoritative immediate preserved terminal-reviewed version in the same delivery chain",
                            path=location,
                        )
                    )

        if review_item is None:
            continue
        approval, approval_path = review_item
        delivery_hash = sha256_file(path)
        if is_current_delivery and approval.get("superseded_by_approval_id"):
            errors.append(
                issue(
                    "APPROVAL_MISSING",
                    "Current delivery cannot be bound to a superseded approval",
                    path=canonical_relpath(approval_path, project_root),
                )
            )
        if isinstance(delivery.get("version"), int) and delivery["version"] >= 2:
            predecessor = delivery.get("supersedes_delivery") if isinstance(delivery.get("supersedes_delivery"), dict) else {}
            predecessor_approval_item = approvals.get(predecessor.get("approval_id"))
            predecessor_approval = predecessor_approval_item[0] if predecessor_approval_item is not None else {}
            if (
                approval.get("supersedes_approval_id") != predecessor.get("approval_id")
                or predecessor_approval.get("superseded_by_approval_id")
                != approval.get("approval_id")
            ):
                errors.append(
                    issue(
                        "DELIVERY_APPROVAL_CHAIN_INVALID",
                        "Delivery revision approval must bidirectionally replace the immediate predecessor approval",
                        path=location,
                    )
                )
        if (
            approval.get("project_id") != project.get("project_id")
            or approval.get("subject_type") != "DELIVERY"
            or approval.get("subject_id") != delivery.get("delivery_id")
            or approval.get("subject_sha256") != delivery_hash
            or approval.get("gate") != "FINISH"
            or approval.get("review_status") not in {
                "USER_REVIEW_REQUIRED",
                "USER_APPROVED",
                "REJECTED",
                "SUPERSEDED",
                "EXCLUDED_FROM_INPUTS",
            }
        ):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Delivery approval does not bind the current delivery record", path=canonical_relpath(approval_path, project_root)))
        required = {(location, delivery_hash.casefold())} | qa_pairs
        if isinstance(export.get("path"), str) and isinstance(export_hash, str):
            required.add((export["path"].replace("\\", "/"), export_hash.casefold()))
        approval_pairs = {
            (item.get("path", "").replace("\\", "/"), str(item.get("sha256", "")).casefold())
            for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) and isinstance(item, dict)
        }
        if not required.issubset(approval_pairs):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Delivery approval evidence must include delivery.json, export, and all QA evidence", path=canonical_relpath(approval_path, project_root)))


def _check_approval_gates(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    approvals_by_id = {
        approval.get("approval_id"): (approval, path)
        for approval, path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    contracts = {
        "assets": ("ASSET", "ASSET_LOCK", "output"),
        "takes": ("TAKE", "RAW_VIDEO", "output"),
    }

    def record_is_current(group: str, path: Path) -> bool:
        if group not in {"storyboards", "source_manifests", "timelines"}:
            return True
        authority_specs = {
            "storyboards": ("storyboard", "02_storyboard/storyboard.json"),
            "source_manifests": ("source_manifest", "06_source_library/source_manifest.json"),
            "timelines": ("timeline", "07_edit/timeline.json"),
        }
        authority_key, default = authority_specs[group]
        try:
            current = authority_path(project_root, project, authority_key, default)
        except ValueError:
            return False
        return path.resolve() == current.resolve()

    for group, (subject_type, gate, binding_kind) in contracts.items():
        for record, path in records[group]:
            identifier = record_id(record)
            if not identifier:
                continue
            expected_path = _production_subject_path(project_root, group, record, path)
            if expected_path is None:
                continue
            candidates = find_bound_approvals(
                project_root,
                records["approvals"],
                project_id=str(project.get("project_id", "")),
                subject_type=subject_type,
                subject_id=identifier,
                gate=gate,
                target_path=expected_path,
                statuses=REVIEW_READY_APPROVAL_STATUSES,
                require_current=True,
            )
            if not candidates:
                continue
            if len(candidates) != 1:
                errors.append(
                    issue(
                        "APPROVAL_MISSING",
                        f"Review-ready {group[:-1]} must resolve to exactly one current central review package: {identifier}",
                        path=canonical_relpath(path, project_root),
                    )
                )
                continue
            approval, approval_path = candidates[0]
            subject_hash = approval.get("subject_sha256")
            expected_hash = None
            if group == "takes":
                expected_hash = record.get("output_sha256")
                remote = record.get("remote") if isinstance(record.get("remote"), dict) else {}
                model = record.get("model") if isinstance(record.get("model"), dict) else {}
                diagnosis = record.get("diagnosis") if isinstance(record.get("diagnosis"), dict) else {}
                if (
                    not record.get("coverage_requirement_ids")
                    or not record.get("input_hashes")
                    or model.get("verified") is not True
                    or diagnosis.get("verdict") != "PASS"
                    or diagnosis.get("first_failure") is not None
                    or not diagnosis.get("what_held")
                ):
                    errors.append(
                        issue(
                            "E_UNAPPROVED_INPUT",
                            f"Review-ready take lacks coverage, input hashes, verified model, or PASS diagnosis: {identifier}",
                            path=canonical_relpath(path, project_root),
                        )
                    )
                origin = record.get("execution_origin")
                if origin == "REMOTE_GENERATION":
                    if remote.get("verified") is not True or not remote.get("job_id") or model.get("verified") is not True:
                        errors.append(issue("E_REMOTE_PROOF_MISSING", f"USER_APPROVED remote take lacks a consistent offline model/remote evidence record: {identifier}", path=canonical_relpath(path, project_root)))
                    if record.get("remote_job_id") and remote.get("job_id") and record.get("remote_job_id") != remote.get("job_id"):
                        errors.append(issue("E_REMOTE_PROOF_MISSING", f"remote_job_id disagrees with remote.job_id: {identifier}", path=canonical_relpath(path, project_root)))
                elif origin == "LOCAL_PROCESSING":
                    lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
                    if (
                        remote.get("verified") is not False
                        or remote.get("job_id") is not None
                        or record.get("remote_job_id") is not None
                        or model.get("verified") is not True
                        or not model.get("version")
                        or not record.get("generation_parameters")
                        or not record.get("input_hashes")
                        or not (lineage.get("parent_take_id") or lineage.get("source_take_ids") or lineage.get("source_asset_ids"))
                    ):
                        errors.append(issue("E_UNAPPROVED_INPUT", f"USER_APPROVED local take lacks local provenance: {identifier}", path=canonical_relpath(path, project_root)))
                else:
                    errors.append(issue("E_UNAPPROVED_INPUT", f"USER_APPROVED take has unknown execution_origin: {identifier}", path=canonical_relpath(path, project_root)))
            elif group == "assets":
                lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
                expected_hash = lineage.get("output_sha256")
                files = record.get("files") if isinstance(record.get("files"), dict) else {}
                master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
            if (
                not isinstance(subject_hash, str)
                or len(subject_hash) != 64
                or not isinstance(expected_hash, str)
                or expected_hash.casefold() != subject_hash.casefold()
                or expected_path is None
                or not expected_path.is_file()
                or sha256_file(expected_path).casefold() != subject_hash.casefold()
            ):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval is not bound to the current authoritative bytes for {identifier}", path=canonical_relpath(approval_path, project_root)))
                continue
            evidence = approval.get("evidence") if isinstance(approval.get("evidence"), list) else []
            exact_evidence = False
            for evidence_item in evidence:
                if not isinstance(evidence_item, dict) or evidence_item.get("sha256") != subject_hash:
                    continue
                evidence_path = _safe_record_path(project_root, evidence_item.get("path"), approval_path, errors)
                if evidence_path == expected_path and evidence_path.is_file() and sha256_file(evidence_path) == subject_hash:
                    exact_evidence = True
                elif evidence_path is not None:
                    errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval evidence bytes no longer match: {identifier}", path=canonical_relpath(evidence_path, project_root)))
            if not exact_evidence:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval evidence does not identify the exact current authority for {identifier}", path=canonical_relpath(approval_path, project_root)))
            record_hash = sha256_file(path) if path.is_file() else None
            record_relative = canonical_relpath(path, project_root)
            if not any(
                isinstance(item, dict)
                and item.get("path") == record_relative
                and item.get("sha256") == record_hash
                for item in evidence
            ):
                errors.append(
                    issue(
                        "E_APPROVAL_HASH_MISMATCH",
                        f"Review-ready {group[:-1]} approval must include its immutable record JSON bytes: {identifier}",
                        path=canonical_relpath(approval_path, project_root),
                    )
                )


def _check_completion(
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    complete = project.get("current_stage") == "COMPLETE" or project.get("project_status") == "COMPLETED"
    if not complete:
        return
    gates = project.get("stage_gates") if isinstance(project.get("stage_gates"), dict) else {}
    if any(gates.get(stage) != "USER_APPROVED" for stage in STAGE_ORDER):
        errors.append(issue("E_STAGE_PREREQ", "COMPLETE/COMPLETED requires every stage gate USER_APPROVED", path="project.json"))
    active = project.get("active_approval_ids")
    approved_by_id = {
        approval.get("approval_id"): approval
        for approval, _ in records["approvals"]
        if approval.get("review_status") == "USER_APPROVED"
        and approval.get("project_id") == project.get("project_id")
        and isinstance(approval.get("approval_id"), str)
    }
    active_set = set(active) if isinstance(active, list) else set()
    active_gates = {
        approved_by_id[approval_id].get("gate")
        for approval_id in active_set
        if approval_id in approved_by_id
    }
    active_approvals = [approved_by_id[approval_id] for approval_id in active_set if approval_id in approved_by_id]
    gate_counts = {
        gate: sum(
            approval.get("gate") == gate
            and approval.get("subject_type") == GATE_SUBJECT_TYPES[gate]
            for approval in active_approvals
        )
        for gate in STAGE_ORDER
    }
    collection_gates = {"ASSET_LOCK", "SHOT_STILL", "RAW_VIDEO"}
    if (
        not isinstance(active, list)
        or len(active_set) < len(STAGE_ORDER)
        or not active_set.issubset(approved_by_id)
        or not set(STAGE_ORDER).issubset(active_gates)
        or any(
            (count < 1 if gate in collection_gates else count != 1)
            for gate, count in gate_counts.items()
        )
    ):
        errors.append(issue("E_STAGE_PREREQ", "COMPLETE/COMPLETED requires active USER_APPROVED approvals covering every gate", path="project.json"))


def _check_authority_targets(
    project_root: Path,
    project: dict,
    errors: list[dict],
) -> None:
    """Require every declared v2 authority pointer to resolve to its expected kind."""

    authorities = project.get("authority_files")
    if not isinstance(authorities, dict):
        return
    directory_keys = {"asset_records_root"}
    for key, raw_path in authorities.items():
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        try:
            target = safe_project_path(project_root, raw_path)
        except ValueError as exc:
            errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
            continue
        exists_as_expected = target.is_dir() if key in directory_keys else target.is_file()
        if not exists_as_expected:
            expected_kind = "directory" if key in directory_keys else "file"
            errors.append(
                issue(
                    "AUTHORITY_TARGET_MISSING",
                    f"Declared authority {key} must exist as a {expected_kind}",
                    path=raw_path.replace("\\", "/"),
                )
            )


def _check_paths(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    def check(raw_path: object, record_path: Path) -> None:
        _safe_record_path(project_root, raw_path, record_path, errors)

    for key in ("authority_files", "paths"):
        mapping = project.get(key)
        if isinstance(mapping, dict):
            for raw_path in mapping.values():
                check(raw_path, project_root / "project.json")
    for asset, path in records["assets"]:
        files = asset.get("files") if isinstance(asset.get("files"), dict) else {}
        for slot in files.values():
            if isinstance(slot, dict):
                check(slot.get("path"), path)
        lineage = asset.get("lineage") if isinstance(asset.get("lineage"), dict) else {}
        for raw_path in lineage.get("source_files", []) if isinstance(lineage.get("source_files"), list) else []:
            check(raw_path, path)
        for item in lineage.get("input_hashes", []) if isinstance(lineage.get("input_hashes"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
    for take, path in records["takes"]:
        check(take.get("output_file"), path)
        for item in take.get("input_hashes", []) if isinstance(take.get("input_hashes"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
        remote = take.get("remote") if isinstance(take.get("remote"), dict) else {}
        for item in remote.get("evidence", []) if isinstance(remote.get("evidence"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
    for approval, path in records["approvals"]:
        for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
    for source, path in records["sources"]:
        check(source.get("path"), path)
    for shot, path in records["shots"]:
        for item in shot.get("still_evidence", []) if isinstance(shot.get("still_evidence"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
    for timeline, path in records["timelines"]:
        for clip in timeline.get("clips", []) if isinstance(timeline.get("clips"), list) else []:
            if isinstance(clip, dict):
                check(clip.get("source_file"), path)
    for delivery, path in records["deliveries"]:
        source = delivery.get("source_timeline") if isinstance(delivery.get("source_timeline"), dict) else {}
        export = delivery.get("export") if isinstance(delivery.get("export"), dict) else {}
        predecessor = delivery.get("supersedes_delivery") if isinstance(delivery.get("supersedes_delivery"), dict) else {}
        check(source.get("path"), path)
        check(export.get("path"), path)
        check(predecessor.get("path"), path)
        derivation = delivery.get("derivation") if isinstance(delivery.get("derivation"), dict) else {}
        for item in derivation.get("input_hashes", []) if isinstance(derivation.get("input_hashes"), list) else []:
            if isinstance(item, dict):
                check(item.get("path"), path)
        for item in _iter_qa_evidence(delivery):
            check(item.get("path"), path)


def _check_ids_and_lineage(
    project_root: Path,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    assets_by_id = {asset.get("asset_id"): (asset, path) for asset, path in records["assets"] if asset.get("asset_id")}
    asset_ids = set(assets_by_id)
    takes_by_id = {take.get("take_id"): (take, path) for take, path in records["takes"] if take.get("take_id")}
    take_ids = set(takes_by_id)

    def authoritative_output(record: dict, record_path: Path, *, is_asset: bool) -> tuple[Path | None, str | None]:
        if is_asset:
            files = record.get("files") if isinstance(record.get("files"), dict) else {}
            master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
            lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
            return _safe_record_path(project_root, master.get("path"), record_path, errors), lineage.get("output_sha256") or master.get("sha256")
        return _safe_record_path(project_root, record.get("output_file"), record_path, errors), record.get("output_sha256")

    def has_input_binding(child: dict, child_path: Path, source_path: Path | None, source_hash: str | None, *, asset: bool) -> bool:
        lineage = child.get("lineage") if isinstance(child.get("lineage"), dict) else {}
        input_hashes = lineage.get("input_hashes", []) if asset else child.get("input_hashes", [])
        if source_path is None or not isinstance(source_hash, str) or not isinstance(input_hashes, list):
            return False
        for item in input_hashes:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            resolved = _safe_record_path(project_root, item.get("path"), child_path, errors)
            if resolved == source_path and str(item.get("sha256", "")).casefold() == source_hash.casefold():
                return True
        return False
    for shot, path in records["shots"]:
        shot_id = shot.get("shot_id")
        scene_id = shot.get("scene_id")
        expected_scene = shot_id.split("_SH", 1)[0] if isinstance(shot_id, str) and "_SH" in shot_id else None
        if expected_scene and scene_id != expected_scene:
            errors.append(issue("ID_PREFIX_MISMATCH", f"{shot_id} must belong to scene {expected_scene}", path=canonical_relpath(path, project_root)))
        duration = shot.get("duration_seconds")
        if duration is not None and (not isinstance(duration, (int, float)) or duration <= 0):
            errors.append(issue("INVALID_DURATION", f"Shot duration must be positive: {shot_id}", path=canonical_relpath(path, project_root)))
    for asset, path in records["assets"]:
        lineage = asset.get("lineage") if isinstance(asset.get("lineage"), dict) else {}
        derivation = lineage.get("derivation")
        parent = lineage.get("parent_asset_id")
        master = lineage.get("immutable_master_asset_id")
        if derivation in {"PATCH_FROM_MASTER", "CROP_FROM_MASTER"}:
            if not parent or parent not in asset_ids or not master or master not in asset_ids:
                errors.append(issue("LINEAGE_PARENT_MISSING", f"Derived asset lacks canonical parent/master: {asset.get('asset_id')}", path=canonical_relpath(path, project_root)))
            if not lineage.get("source_files") or not lineage.get("input_hashes"):
                errors.append(issue("LINEAGE_INPUT_MISSING", f"Derived asset lacks source/input hashes: {asset.get('asset_id')}", path=canonical_relpath(path, project_root)))
        source_asset_ids = {value for value in (parent, master) if isinstance(value, str)}
        for source_id in source_asset_ids:
            source_item = assets_by_id.get(source_id)
            if source_item is None:
                errors.append(issue("LINEAGE_PARENT_MISSING", f"Unknown source asset {source_id} for {asset.get('asset_id')}", path=canonical_relpath(path, project_root)))
                continue
            source_record, source_record_path = source_item
            source_path, source_hash = authoritative_output(source_record, source_record_path, is_asset=True)
            if not has_input_binding(asset, path, source_path, source_hash, asset=True):
                errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Asset input does not bind authoritative source {source_id}: {asset.get('asset_id')}", path=canonical_relpath(path, project_root)))
    for take, path in records["takes"]:
        take_id = take.get("take_id")
        shot_id = take.get("shot_id")
        expected_shot = take_id.rsplit("_T", 1)[0] if isinstance(take_id, str) and "_T" in take_id else None
        if expected_shot and shot_id != expected_shot:
            errors.append(issue("ID_PREFIX_MISMATCH", f"{take_id} must belong to shot {expected_shot}", path=canonical_relpath(path, project_root)))
        lineage = take.get("lineage") if isinstance(take.get("lineage"), dict) else {}
        derivation = lineage.get("derivation")
        if derivation and derivation != "GENERATED":
            parents = [lineage.get("parent_take_id")] + list(lineage.get("source_take_ids", []) if isinstance(lineage.get("source_take_ids"), list) else [])
            source_assets = lineage.get("source_asset_ids", []) if isinstance(lineage.get("source_asset_ids"), list) else []
            if not any(parent in take_ids for parent in parents if parent) and not any(asset in asset_ids for asset in source_assets):
                errors.append(issue("LINEAGE_PARENT_MISSING", f"Derived take lacks an existing source: {take_id}", path=canonical_relpath(path, project_root)))
            diagnosis = take.get("diagnosis") if isinstance(take.get("diagnosis"), dict) else {}
            if diagnosis.get("verdict") in {None, "NOT_REVIEWED"}:
                errors.append(issue("DIAGNOSIS_NOT_REVIEWED", f"Derived take diagnosis is not reviewed: {take_id}", path=canonical_relpath(path, project_root)))
            for source_id in {value for value in parents if isinstance(value, str)}:
                source_item = takes_by_id.get(source_id)
                if source_item is None:
                    continue
                source_record, source_record_path = source_item
                source_path, source_hash = authoritative_output(source_record, source_record_path, is_asset=False)
                if not has_input_binding(take, path, source_path, source_hash, asset=False):
                    errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Take input does not bind authoritative parent take {source_id}: {take_id}", path=canonical_relpath(path, project_root)))
            for source_id in {value for value in source_assets if isinstance(value, str)}:
                source_item = assets_by_id.get(source_id)
                if source_item is None:
                    continue
                source_record, source_record_path = source_item
                source_path, source_hash = authoritative_output(source_record, source_record_path, is_asset=True)
                if not has_input_binding(take, path, source_path, source_hash, asset=False):
                    errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Take input does not bind authoritative source asset {source_id}: {take_id}", path=canonical_relpath(path, project_root)))


def _check_source_and_timeline(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    try:
        current_timeline_path = authority_path(
            project_root,
            project,
            "timeline",
            "07_edit/timeline.json",
        ).resolve()
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        current_timeline_path = None
    source_ids: set[str] = set()
    for source, path in records["sources"]:
        source_id = source.get("source_id")
        if not isinstance(source_id, str):
            errors.append(
                issue(
                    "INVALID_RECORD",
                    "Source source_id must be a string",
                    path=canonical_relpath(path, project_root),
                )
            )
            continue
        if source_id in source_ids:
            errors.append(issue("DUPLICATE_SOURCE_ID", f"Duplicate source_id: {source_id}", path=canonical_relpath(path, project_root)))
        source_ids.add(source_id)
    takes_by_id = {
        take.get("take_id"): (take, take_path)
        for take, take_path in records["takes"]
        if isinstance(take.get("take_id"), str) and take.get("take_id")
    }
    for source, path in records["sources"]:
        take_item = takes_by_id.get(source.get("take_id"))
        if take_item is None:
            errors.append(issue("UNKNOWN_TAKE", f"Source references unknown take: {source.get('take_id')}", path=canonical_relpath(path, project_root)))
            continue
        take, take_path = take_item
        output_path = _production_subject_path(project_root, "takes", take, take_path)
        take_approvals = (
            _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="TAKE",
                subject_id=take.get("take_id"),
                gate="RAW_VIDEO",
                target_path=output_path,
                statuses={"USER_APPROVED"},
            )
            if output_path is not None
            else []
        )
        if (
            len(take_approvals) != 1
            or source.get("source_status") != "SOURCE_APPROVED"
            or take.get("output_sha256") != source.get("sha256")
            or take.get("output_file") != source.get("path")
        ):
            errors.append(issue("E_UNAPPROVED_INPUT", f"Source is not bound to a USER_APPROVED take: {source.get('source_id')}", path=canonical_relpath(path, project_root)))
        raw_path = source.get("path")
        if isinstance(raw_path, str):
            resolved = _safe_record_path(project_root, raw_path, path, errors)
            if resolved is not None and (not resolved.is_file() or sha256_file(resolved) != source.get("sha256")):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Source bytes mismatch: {source.get('source_id')}", path=canonical_relpath(path, project_root)))
    for manifest, path in records["source_manifests"]:
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="SOURCE_LIBRARY",
            subject_id=manifest.get("library_id"),
            gate="SOURCE_LIBRARY",
            target_path=path,
            statuses={
                "USER_REVIEW_REQUIRED",
                "USER_APPROVED",
                "REJECTED",
                "SUPERSEDED",
                "EXCLUDED_FROM_INPUTS",
            },
        )
        if review_matches and (
            manifest.get("lock_status") != "SOURCE_LOCKED"
            or not manifest.get("sources")
        ):
            errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", "A centrally reviewed source library must already be SOURCE_LOCKED and nonempty", path=canonical_relpath(path, project_root)))
    for timeline, path in records["timelines"]:
        is_current_timeline = (
            current_timeline_path is not None
            and path.resolve() == current_timeline_path
        )
        tracks = timeline.get("tracks", []) if isinstance(timeline.get("tracks"), list) else []
        track_id_values = [
            track.get("track_id")
            for track in tracks
            if isinstance(track, dict) and isinstance(track.get("track_id"), str)
        ]
        track_order_values = [
            track.get("order")
            for track in tracks
            if isinstance(track, dict)
            and isinstance(track.get("order"), int)
            and not isinstance(track.get("order"), bool)
        ]
        if len(track_id_values) != len(tracks) or len(track_order_values) != len(tracks):
            errors.append(
                issue(
                    "INVALID_RECORD",
                    "Timeline tracks require string track_id and integer order values",
                    path=canonical_relpath(path, project_root),
                )
            )
        track_ids = set(track_id_values)
        if len(track_id_values) != len(set(track_id_values)) or len(track_order_values) != len(set(track_order_values)):
            errors.append(issue("DUPLICATE_ID", "Timeline track IDs and orders must be unique", path=canonical_relpath(path, project_root)))
        clips = timeline.get("clips", []) if isinstance(timeline.get("clips"), list) else []
        clip_ids = [
            clip.get("clip_id")
            for clip in clips
            if isinstance(clip, dict) and isinstance(clip.get("clip_id"), str)
        ]
        if len(clip_ids) != len(clips):
            errors.append(issue("INVALID_RECORD", "Timeline clips require string clip_id values", path=canonical_relpath(path, project_root)))
        if len(clip_ids) != len(set(clip_ids)):
            errors.append(issue("DUPLICATE_ID", "Timeline clip IDs must be unique", path=canonical_relpath(path, project_root)))
        events = timeline.get("events", []) if isinstance(timeline.get("events"), list) else []
        event_ids = [
            event.get("event_id")
            for event in events
            if isinstance(event, dict) and isinstance(event.get("event_id"), str)
        ]
        if len(event_ids) != len(events):
            errors.append(issue("INVALID_RECORD", "Timeline events require string event_id values", path=canonical_relpath(path, project_root)))
        if len(event_ids) != len(set(event_ids)):
            errors.append(issue("DUPLICATE_ID", "Timeline event IDs must be unique", path=canonical_relpath(path, project_root)))
        event_id_set = set(event_ids)
        intervals_by_track: dict[str, list[tuple[int, int, str | None]]] = {}
        source_by_id = {
            source.get("source_id"): source
            for source, _ in records["sources"]
            if isinstance(source.get("source_id"), str)
        }
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            clip_track_id = clip.get("track_id")
            if not isinstance(clip_track_id, str) or clip_track_id not in track_ids:
                errors.append(issue("UNKNOWN_TRACK", f"Clip references unknown track: {clip.get('track_id')}", path=canonical_relpath(path, project_root)))
            clip_source_id = clip.get("source_id")
            if is_current_timeline and (
                not isinstance(clip_source_id, str) or clip_source_id not in source_ids
            ):
                errors.append(issue("UNKNOWN_SOURCE", f"Clip references unknown source: {clip.get('source_id')}", path=canonical_relpath(path, project_root)))
            for event_id in clip.get("linked_event_ids", []) if isinstance(clip.get("linked_event_ids"), list) else []:
                if not isinstance(event_id, str) or event_id not in event_id_set:
                    errors.append(issue("UNKNOWN_EVENT", f"Clip references unknown timeline event: {event_id}", path=canonical_relpath(path, project_root)))
            for prefix in ("source", "timeline"):
                start, end = clip.get(f"{prefix}_in_frame"), clip.get(f"{prefix}_out_frame")
                if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                    errors.append(issue("INVALID_FRAME_RANGE", f"Invalid {prefix} range in {clip.get('clip_id')}", path=canonical_relpath(path, project_root)))
            timeline_start, timeline_end = clip.get("timeline_in_frame"), clip.get("timeline_out_frame")
            if isinstance(timeline_start, int) and isinstance(timeline_end, int) and timeline_end > timeline_start and isinstance(clip.get("track_id"), str):
                intervals_by_track.setdefault(clip["track_id"], []).append((timeline_start, timeline_end, clip.get("clip_id")))
            source = source_by_id.get(clip_source_id) if isinstance(clip_source_id, str) else None
            expected_hash = source.get("sha256") if source else None
            expected_path = source.get("path") if source else None
            if is_current_timeline and expected_path is not None and clip.get("source_file") != expected_path:
                errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Timeline clip source_file is not the authoritative source path: {clip.get('clip_id')}", path=canonical_relpath(path, project_root)))
            if timeline.get("lock_status") == "PICTURE_LOCKED":
                if is_current_timeline and (
                    clip.get("review_status") != "USER_APPROVED"
                    or not expected_hash
                    or clip.get("source_sha256") != expected_hash
                ):
                    errors.append(issue("E_UNAPPROVED_INPUT", f"Locked timeline clip is not approval/hash bound: {clip.get('clip_id')}", path=canonical_relpath(path, project_root)))
                elif not is_current_timeline:
                    preserved_source = _safe_record_path(
                        project_root,
                        clip.get("source_file"),
                        path,
                        errors,
                    )
                    preserved_hash = clip.get("source_sha256")
                    if (
                        clip.get("review_status") != "USER_APPROVED"
                        or preserved_source is None
                        or not preserved_source.is_file()
                        or not isinstance(preserved_hash, str)
                        or sha256_file(preserved_source) != preserved_hash
                    ):
                        errors.append(
                            issue(
                                "E_APPROVAL_HASH_MISMATCH",
                                f"Historical locked timeline clip source bytes/hash are not preserved: {clip.get('clip_id')}",
                                path=canonical_relpath(path, project_root),
                            )
                        )
        for track_id, intervals in intervals_by_track.items():
            previous_end = -1
            for start, end, clip_id in sorted(intervals):
                if start < previous_end:
                    errors.append(issue("TIMELINE_OVERLAP", f"Timeline clips overlap on track {track_id}: {clip_id}", path=canonical_relpath(path, project_root)))
                previous_end = max(previous_end, end)
        maximum_frame = max((end for intervals in intervals_by_track.values() for _, end, _ in intervals), default=0)
        for event in events:
            if not isinstance(event, dict):
                continue
            frame = event.get("frame")
            if isinstance(frame, int) and maximum_frame and frame > maximum_frame:
                errors.append(issue("INVALID_FRAME_RANGE", f"Timeline event is outside the edited duration: {event.get('event_id')}", path=canonical_relpath(path, project_root)))


def _check_timeline_revisions(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    try:
        current_path = authority_path(project_root, project, "timeline", "07_edit/timeline.json")
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        return
    timelines = {
        (timeline.get("timeline_id"), timeline.get("version")): (timeline, path.resolve())
        for timeline, path in records["timelines"]
        if isinstance(timeline.get("timeline_id"), str) and isinstance(timeline.get("version"), int)
    }
    approvals = {
        approval.get("approval_id"): (approval, approval_path.resolve())
        for approval, approval_path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    current_timelines = [
        (timeline, path.resolve())
        for timeline, path in records["timelines"]
        if path.resolve() == current_path.resolve()
    ]
    if records["timelines"] and len(current_timelines) != 1:
        errors.append(issue("TIMELINE_POINTER_INVALID", "project.authority_files.timeline does not select a discovered timeline record", path="project.json"))
    elif current_timelines and isinstance(current_timelines[0][0].get("timeline_id"), str):
        current_timeline = current_timelines[0][0]
        current_id = current_timeline["timeline_id"]
        versions = [
            item.get("version")
            for item, _ in records["timelines"]
            if item.get("timeline_id") == current_id and isinstance(item.get("version"), int)
        ]
        if versions and current_timeline.get("version") != max(versions):
            errors.append(
                issue(
                    "TIMELINE_POINTER_INVALID",
                    "project.authority_files.timeline must select the newest timeline revision in its chain",
                    path="project.json",
                )
            )

    for timeline, path in records["timelines"]:
        location = canonical_relpath(path, project_root)
        timeline_id, version = timeline.get("timeline_id"), timeline.get("version")
        locked = timeline.get("lock_status") == "PICTURE_LOCKED"
        is_current_timeline = path.resolve() == current_path.resolve()
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="TIMELINE",
            subject_id=timeline_id,
            gate="EDIT",
            target_path=path,
            statuses={
                "USER_REVIEW_REQUIRED",
                "USER_APPROVED",
                "REJECTED",
                "SUPERSEDED",
                "EXCLUDED_FROM_INPUTS",
            },
            require_current=is_current_timeline,
        )
        if len(review_matches) > 1:
            errors.append(issue("E_STAGE_PREREQ", "Timeline has multiple applicable central decisions", path=location))
        review_item = review_matches[0] if len(review_matches) == 1 else None
        if review_item is not None and not locked:
            errors.append(issue("TIMELINE_LOCK_INVALID", "A centrally reviewed timeline must already be PICTURE_LOCKED", path=location))
        if version == 1:
            if location != "07_edit/timeline.json" or timeline.get("supersedes_timeline") is not None:
                errors.append(issue("TIMELINE_PREDECESSOR_INVALID", "Timeline v1 must remain at 07_edit/timeline.json with no predecessor", path=location))
            continue
        if not isinstance(version, int) or version < 2 or not isinstance(timeline_id, str):
            continue
        expected_location = f"07_edit/records/{timeline_id}/v{version:03d}/timeline.json"
        if location != expected_location:
            errors.append(issue("TIMELINE_POINTER_INVALID", f"Timeline v2+ must use immutable versioned path {expected_location}", path=location))
        predecessor = timeline.get("supersedes_timeline") if isinstance(timeline.get("supersedes_timeline"), dict) else {}
        predecessor_item = timelines.get((timeline_id, version - 1))
        predecessor_path = _safe_record_path(project_root, predecessor.get("path"), path, errors)
        valid = predecessor_item is not None and predecessor_path is not None
        predecessor_approval: dict = {}
        if valid:
            predecessor_record, authoritative_predecessor_path = predecessor_item
            predecessor_hash = sha256_file(authoritative_predecessor_path) if authoritative_predecessor_path.is_file() else None
            approval_item = approvals.get(predecessor.get("approval_id"))
            approval = approval_item[0] if approval_item is not None else {}
            approval_path = approval_item[1] if approval_item is not None else None
            predecessor_approval = approval
            bound_predecessor_approvals = _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="TIMELINE",
                subject_id=timeline_id,
                gate="EDIT",
                target_path=authoritative_predecessor_path,
                statuses={"USER_APPROVED", "REJECTED"},
                require_current=False,
            )
            valid = (
                predecessor.get("timeline_id") == timeline_id
                and predecessor.get("version") == version - 1
                and predecessor_path == authoritative_predecessor_path
                and predecessor.get("sha256") == predecessor_hash
                and predecessor_record.get("lock_status") == "PICTURE_LOCKED"
                and approval.get("project_id") == project.get("project_id")
                and approval.get("approval_id") == predecessor.get("approval_id")
                and approval.get("subject_type") == "TIMELINE"
                and approval.get("subject_id") == timeline_id
                and approval.get("subject_sha256") == predecessor_hash
                and approval.get("review_status") in {"USER_APPROVED", "REJECTED"}
                and approval_path is not None
                and approval_path.is_file()
                and len(bound_predecessor_approvals) == 1
                and bound_predecessor_approvals[0][0].get("approval_id") == predecessor.get("approval_id")
            )
        if not valid:
            errors.append(issue("TIMELINE_PREDECESSOR_INVALID", "Timeline predecessor is missing, mutable, unapproved, or identity/path/hash mismatched", path=location))
        if review_item is not None:
            current_approval, current_approval_path = review_item
            current_hash = sha256_file(path) if path.is_file() else None
            approval_chain_valid = (
                isinstance(current_hash, str)
                and current_approval.get("project_id") == project.get("project_id")
                and current_approval.get("subject_type") == "TIMELINE"
                and current_approval.get("subject_id") == timeline_id
                and current_approval.get("subject_sha256") == current_hash
                and current_approval.get("supersedes_approval_id") == predecessor.get("approval_id")
                and predecessor_approval.get("approval_id") == predecessor.get("approval_id")
                and predecessor_approval.get("superseded_by_approval_id") == current_approval.get("approval_id")
                and current_approval_path is not None
                and current_approval_path.is_file()
            )
            if not approval_chain_valid:
                errors.append(
                    issue(
                        "TIMELINE_APPROVAL_CHAIN_INVALID",
                        "Timeline revision approval must bidirectionally replace the immediate predecessor approval",
                        path=location,
                    )
                )


def _check_storyboards(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    approvals = {
        approval.get("approval_id"): (approval, approval_path)
        for approval, approval_path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }
    try:
        story_path = authority_path(project_root, project, "story_contract", "01_story/STORY_CONTRACT.md")
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        story_path = None
    for storyboard, path in records["storyboards"]:
        location = canonical_relpath(path, project_root)
        review_matches = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="STORYBOARD",
            subject_id=storyboard.get("storyboard_id"),
            gate="STORYBOARD",
            target_path=path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        if len(review_matches) > 1:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    "Current storyboard has multiple active review decisions",
                    path=location,
                )
            )
        review_item = review_matches[0] if len(review_matches) == 1 else None
        review_ready = review_item is not None
        planned_assets: set[str] = set()
        for planned in storyboard.get("asset_plan", []) if isinstance(storyboard.get("asset_plan"), list) else []:
            if not isinstance(planned, dict) or not isinstance(planned.get("asset_id"), str):
                continue
            asset_id = planned["asset_id"]
            if asset_id in planned_assets:
                errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard asset_plan ID: {asset_id}", path=location))
            planned_assets.add(asset_id)

        scenes = storyboard.get("scenes") if isinstance(storyboard.get("scenes"), list) else []
        scene_ids: set[str] = set()
        scene_orders: set[int] = set()
        panel_ids: set[str] = set()
        panel_scene: dict[str, str] = {}
        panel_evidence: set[tuple[str, str]] = set()
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_id = scene.get("scene_id")
            if isinstance(scene_id, str):
                if scene_id in scene_ids:
                    errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard scene ID: {scene_id}", path=location))
                scene_ids.add(scene_id)
            scene_order = scene.get("order")
            if isinstance(scene_order, int):
                if scene_order in scene_orders:
                    errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard scene order: {scene_order}", path=location))
                scene_orders.add(scene_order)
            panel_orders: set[int] = set()
            panels = scene.get("panels") if isinstance(scene.get("panels"), list) else []
            for panel in panels:
                if not isinstance(panel, dict):
                    continue
                panel_id = panel.get("panel_id")
                if isinstance(panel_id, str):
                    if panel_id in panel_ids:
                        errors.append(issue("DUPLICATE_PANEL_ID", f"Duplicate panel_id: {panel_id}", path=location))
                    panel_ids.add(panel_id)
                    if isinstance(scene_id, str):
                        panel_scene[panel_id] = scene_id
                        if not panel_id.startswith(f"{scene_id}_P"):
                            errors.append(issue("ID_PREFIX_MISMATCH", f"Panel {panel_id} must belong to scene {scene_id}", path=location))
                panel_order = panel.get("order")
                if isinstance(panel_order, int):
                    if panel_order in panel_orders:
                        errors.append(issue("DUPLICATE_PANEL_ORDER", f"Duplicate storyboard panel order in {scene_id}: {panel_order}", path=location))
                    panel_orders.add(panel_order)
                timing = panel.get("duration_hint_seconds") if isinstance(panel.get("duration_hint_seconds"), dict) else {}
                minimum, preferred, maximum = timing.get("minimum"), timing.get("preferred"), timing.get("maximum")
                if all(isinstance(value, (int, float)) for value in (minimum, preferred, maximum)) and not minimum <= preferred <= maximum:
                    errors.append(issue("INVALID_DURATION_RANGE", f"Panel duration must satisfy minimum <= preferred <= maximum: {panel_id}", path=location))
                action = panel.get("action") if isinstance(panel.get("action"), dict) else {}
                action_path = action.get("path") if isinstance(action.get("path"), dict) else {}
                waypoint_orders: set[int] = set()
                for waypoint in action_path.get("waypoints", []) if isinstance(action_path.get("waypoints"), list) else []:
                    if not isinstance(waypoint, dict) or not isinstance(waypoint.get("order"), int):
                        continue
                    waypoint_order = waypoint["order"]
                    if waypoint_order in waypoint_orders:
                        errors.append(
                            issue(
                                "DUPLICATE_WAYPOINT_ORDER",
                                f"Duplicate action waypoint order in storyboard panel {panel_id}: {waypoint_order}",
                                path=location,
                            )
                        )
                    waypoint_orders.add(waypoint_order)
                for reference in panel.get("active_assets", []) if isinstance(panel.get("active_assets"), list) else []:
                    if not isinstance(reference, dict):
                        continue
                    asset_id = reference.get("asset_id")
                    if asset_id not in planned_assets:
                        errors.append(issue("UNKNOWN_PLANNED_ASSET", f"Storyboard panel references asset outside asset_plan: {asset_id}", path=location))
                if review_ready:
                    image_file, image_hash = panel.get("image_file"), panel.get("image_sha256")
                    image_path = _safe_record_path(project_root, image_file, path, errors)
                    if (
                        image_path is None
                        or not image_path.is_file()
                        or not isinstance(image_hash, str)
                        or sha256_file(image_path).casefold() != image_hash.casefold()
                    ):
                        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Storyboard panel image bytes mismatch: {panel_id}", path=location))
                    elif isinstance(image_file, str):
                        panel_evidence.add((image_file.replace("\\", "/"), image_hash.casefold()))

        shot_ids: set[str] = set()
        shot_orders: dict[str, set[int]] = {}
        covered_scene_ids: set[str] = set()
        coverage_ids: set[str] = set()
        shot_plan = storyboard.get("shot_plan") if isinstance(storyboard.get("shot_plan"), list) else []
        for planned_shot in shot_plan:
            if not isinstance(planned_shot, dict):
                continue
            shot_id, scene_id = planned_shot.get("shot_id"), planned_shot.get("scene_id")
            if isinstance(shot_id, str):
                if shot_id in shot_ids:
                    errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard shot plan ID: {shot_id}", path=location))
                shot_ids.add(shot_id)
                if isinstance(scene_id, str) and not shot_id.startswith(f"{scene_id}_SH"):
                    errors.append(issue("ID_PREFIX_MISMATCH", f"Planned shot {shot_id} must belong to scene {scene_id}", path=location))
            if scene_id not in scene_ids:
                errors.append(issue("E_STAGE_PREREQ", f"Planned shot references unknown scene: {scene_id}", path=location))
            elif isinstance(scene_id, str):
                covered_scene_ids.add(scene_id)
            order = planned_shot.get("order")
            if isinstance(scene_id, str) and isinstance(order, int):
                orders = shot_orders.setdefault(scene_id, set())
                if order in orders:
                    errors.append(issue("DUPLICATE_ID", f"Duplicate planned shot order in {scene_id}: {order}", path=location))
                orders.add(order)
            for panel_id in planned_shot.get("storyboard_panel_ids", []) if isinstance(planned_shot.get("storyboard_panel_ids"), list) else []:
                if panel_id not in panel_ids or panel_scene.get(panel_id) != scene_id:
                    errors.append(issue("UNKNOWN_PANEL", f"Planned shot references unknown or cross-scene panel: {panel_id}", path=location))
            for asset_id in planned_shot.get("required_asset_ids", []) if isinstance(planned_shot.get("required_asset_ids"), list) else []:
                if asset_id not in planned_assets:
                    errors.append(issue("UNKNOWN_PLANNED_ASSET", f"Planned shot references asset outside asset_plan: {asset_id}", path=location))
            for coverage in planned_shot.get("coverage_requirements", []) if isinstance(planned_shot.get("coverage_requirements"), list) else []:
                if not isinstance(coverage, dict) or not isinstance(coverage.get("coverage_id"), str):
                    continue
                coverage_id = coverage["coverage_id"]
                if coverage_id in coverage_ids:
                    errors.append(issue("DUPLICATE_ID", f"Duplicate storyboard coverage requirement ID: {coverage_id}", path=location))
                coverage_ids.add(coverage_id)

        if review_ready:
            for scene_id in sorted(scene_ids - covered_scene_ids):
                errors.append(
                    issue(
                        "UNCOVERED_SCENE",
                        f"Review-ready storyboard scene has no planned shot: {scene_id}",
                        path=location,
                    )
                )

        if review_ready:
            dependency = storyboard.get("story_dependency") if isinstance(storyboard.get("story_dependency"), dict) else {}
            dependency_path = _safe_record_path(project_root, dependency.get("path"), path, errors)
            dependency_hash = dependency.get("sha256")
            approval_item = approvals.get(dependency.get("approval_id"))
            approval = approval_item[0] if approval_item is not None else {}
            if (
                story_path is None
                or dependency_path != story_path.resolve()
                or not story_path.is_file()
                or not isinstance(dependency_hash, str)
                or sha256_file(story_path).casefold() != dependency_hash.casefold()
                or approval.get("project_id") != project.get("project_id")
                or approval.get("subject_type") != "STORY"
                or approval.get("subject_id") != "story-contract"
                or approval.get("subject_sha256") != dependency_hash
                or approval.get("review_status") != "USER_APPROVED"
                or approval.get("superseded_by_approval_id")
            ):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Storyboard story_dependency is not bound to the current USER_APPROVED story authority", path=location))

        if review_item is not None:
            approval, approval_path = review_item
            storyboard_hash = sha256_file(path)
            required = {(location, storyboard_hash.casefold())} | panel_evidence
            actual = {
                (item.get("path", "").replace("\\", "/"), str(item.get("sha256", "")).casefold())
                for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) and isinstance(item, dict)
            }
            if (
                approval.get("project_id") != project.get("project_id")
                or approval.get("subject_type") != "STORYBOARD"
                or approval.get("subject_id") != storyboard.get("storyboard_id")
                or approval.get("subject_sha256") != storyboard_hash
                or not required.issubset(actual)
            ):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Storyboard review evidence must include storyboard.json and every current panel image", path=canonical_relpath(approval_path, project_root)))


def _check_remote_evidence(
    project_root: Path,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    for group in ("assets", "takes"):
        for record, path in records[group]:
            remote = record.get("remote") if isinstance(record.get("remote"), dict) else {}
            if group == "assets" and record.get("element_tag") and remote.get("verified") is not True:
                errors.append(issue("E_REMOTE_PROOF_MISSING", f"element_tag requires a consistent offline remote asset evidence record: {record.get('asset_id')}", path=canonical_relpath(path, project_root)))
            if remote.get("verified") is not True:
                continue
            if group == "assets":
                identifiers_ok = bool(remote.get("remote_asset_id") and remote.get("remote_project_id"))
                identifier = record.get("asset_id")
            else:
                identifiers_ok = bool(remote.get("job_id") and remote.get("project_id"))
                identifier = record.get("take_id")
                if record.get("remote_job_id") and record.get("remote_job_id") != remote.get("job_id"):
                    identifiers_ok = False
            evidence = remote.get("evidence") if isinstance(remote.get("evidence"), list) else []
            if not identifiers_ok or not remote.get("verified_at") or not evidence:
                errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence record lacks IDs, timestamp, or evidence: {identifier}", path=canonical_relpath(path, project_root)))
            for item in evidence:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence is incomplete: {identifier}", path=canonical_relpath(path, project_root)))
                    continue
                evidence_path = _safe_record_path(project_root, item["path"], path, errors)
                if evidence_path is None or not evidence_path.is_file() or sha256_file(evidence_path).casefold() != item["sha256"].casefold():
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence bytes mismatch: {identifier}", path=canonical_relpath(path, project_root)))
                elif (package_error := offline_remote_package_error(evidence_path, record, record_type="ASSET" if group == "assets" else "TAKE")):
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence package is inconsistent for {identifier}: {package_error}", path=canonical_relpath(evidence_path, project_root)))


def _check_local_processing_hashes(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    for take, path in records["takes"]:
        output_path = _production_subject_path(project_root, "takes", take, path)
        review_matches = (
            _bound_content_approvals(
                project_root,
                project,
                records,
                subject_type="TAKE",
                subject_id=take.get("take_id"),
                gate="RAW_VIDEO",
                target_path=output_path,
                statuses=REVIEW_READY_APPROVAL_STATUSES,
            )
            if output_path is not None
            else []
        )
        if take.get("execution_origin") != "LOCAL_PROCESSING" or not review_matches:
            continue
        take_id = take.get("take_id")
        for item in take.get("input_hashes", []) if isinstance(take.get("input_hashes"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local input hash is incomplete: {take_id}", path=canonical_relpath(path, project_root)))
                continue
            input_path = _safe_record_path(project_root, item["path"], path, errors)
            if input_path is None or not input_path.is_file() or sha256_file(input_path).casefold() != item["sha256"].casefold():
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local input bytes mismatch: {take_id}", path=canonical_relpath(path, project_root)))
        output_path = _safe_record_path(project_root, take.get("output_file"), path, errors)
        expected_output = take.get("output_sha256")
        if (
            output_path is None
            or not output_path.is_file()
            or not isinstance(expected_output, str)
            or sha256_file(output_path).casefold() != expected_output.casefold()
        ):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local output bytes mismatch: {take_id}", path=canonical_relpath(path, project_root)))


def _check_approval_replacement_graph(
    project_root: Path,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    """Validate reciprocal, same-subject approval replacement links without mutating history."""

    approvals_by_id: dict[str, list[tuple[dict, Path]]] = {}
    for approval, path in records["approvals"]:
        approval_id = approval.get("approval_id")
        if isinstance(approval_id, str):
            approvals_by_id.setdefault(approval_id, []).append((approval, path))

    fixed_types = {"STORY", "STORYBOARD", "LOOKDEV", "SHOT_STILL", "SOURCE_LIBRARY"}
    contract_fields = ("project_id", "subject_type", "subject_id", "gate")
    for approval_id, items in approvals_by_id.items():
        if len(items) != 1:
            continue
        approval, approval_path = items[0]
        location = canonical_relpath(approval_path, project_root)
        if approval.get("review_status") == "SUPERSEDED" and not approval.get("superseded_by_approval_id"):
            errors.append(
                issue(
                    "APPROVAL_CHAIN_INVALID",
                    f"SUPERSEDED approval must identify its successor: {approval_id}",
                    path=location,
                )
            )
        if (
            approval.get("subject_type") in fixed_types
            and approval.get("superseded_by_approval_id")
            and approval.get("review_status") not in {"SUPERSEDED", "REJECTED"}
        ):
            errors.append(
                issue(
                    "APPROVAL_CHAIN_INVALID",
                    f"Replaced fixed-authority approval must have SUPERSEDED status: {approval_id}",
                    path=location,
                )
            )
        for field, reciprocal in (
            ("supersedes_approval_id", "superseded_by_approval_id"),
            ("superseded_by_approval_id", "supersedes_approval_id"),
        ):
            target_id = approval.get(field)
            if target_id is None:
                continue
            if not isinstance(target_id, str) or target_id == approval_id:
                errors.append(
                    issue(
                        "APPROVAL_CHAIN_INVALID",
                        f"Approval replacement link is invalid or self-referential: {approval_id}.{field}",
                        path=location,
                    )
                )
                continue
            target_items = approvals_by_id.get(target_id, [])
            if len(target_items) != 1:
                errors.append(
                    issue(
                        "APPROVAL_CHAIN_INVALID",
                        f"Approval replacement target does not resolve uniquely: {approval_id} -> {target_id}",
                        path=location,
                    )
                )
                continue
            target, target_path = target_items[0]
            if (
                any(target.get(key) != approval.get(key) for key in contract_fields)
                or target.get(reciprocal) != approval_id
            ):
                errors.append(
                    issue(
                        "APPROVAL_CHAIN_INVALID",
                        f"Approval replacement must be reciprocal and retain project/subject/gate: {approval_id} -> {target_id}",
                        path=canonical_relpath(target_path, project_root),
                    )
                )

    graph = {
        approval_id: items[0][0].get("supersedes_approval_id")
        for approval_id, items in approvals_by_id.items()
        if len(items) == 1 and isinstance(items[0][0].get("supersedes_approval_id"), str)
    }
    state: dict[str, int] = {}
    max_chain_length = 4096
    for approval_id in sorted(graph):
        if state.get(approval_id, 0) == 2:
            continue
        trail: list[str] = []
        position: dict[str, int] = {}
        node = approval_id
        while node in graph and state.get(node, 0) != 2:
            if node in position:
                cycle = trail[position[node] :] + [node]
                errors.append(
                    issue(
                        "APPROVAL_CHAIN_INVALID",
                        f"Approval replacement cycle detected: {' -> '.join(cycle)}",
                        path="09_approvals",
                    )
                )
                break
            if len(trail) >= max_chain_length:
                errors.append(
                    issue(
                        "APPROVAL_CHAIN_INVALID",
                        f"Approval replacement chain exceeds {max_chain_length} records",
                        path="09_approvals",
                    )
                )
                break
            position[node] = len(trail)
            trail.append(node)
            state[node] = 1
            target = graph.get(node)
            if not isinstance(target, str):
                break
            node = target
        for visited in trail:
            state[visited] = 2


def _check_decision_receipts(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    """Require a machine-local authenticated receipt for each explicit terminal decision."""

    project_id = str(project.get("project_id", ""))
    for approval, approval_path in records["approvals"]:
        if approval.get("review_status") not in {"USER_APPROVED", "REJECTED"}:
            continue
        receipt_error = verify_decision_receipt(
            project_root, project_id, approval, approval_path
        )
        if receipt_error is not None:
            errors.append(
                issue(
                    "DECISION_RECEIPT_INVALID",
                    f"Authenticated decision receipt is invalid: {receipt_error}",
                    path=canonical_relpath(approval_path, project_root),
                )
            )


def _archive_prefix(approval: dict) -> tuple[str, ...] | None:
    subject_type = approval.get("subject_type")
    subject_id = approval.get("subject_id")
    if subject_type == "STORY" and subject_id == "story-contract":
        return ("01_story", "history", "story-contract")
    if subject_type == "STORYBOARD" and isinstance(subject_id, str):
        return ("02_storyboard", "history", subject_id)
    if subject_type == "LOOKDEV" and subject_id == "visual-bible":
        return ("03_lookdev", "history", "visual-bible")
    if subject_type == "SHOT_STILL" and isinstance(subject_id, str):
        return ("05_shots", subject_id, "history")
    if subject_type == "SOURCE_LIBRARY" and isinstance(subject_id, str):
        return ("06_source_library", "history", subject_id)
    return None


def _archive_path_parts(raw_path: str, prefix: tuple[str, ...]) -> tuple[str, ...] | None:
    parts = tuple(Path(raw_path).parts)
    if (
        parts[: len(prefix)] != prefix
        or len(parts) <= len(prefix) + 1
        or re.fullmatch(r"v[0-9]{3,}", parts[len(prefix)]) is None
    ):
        return None
    return parts


def _is_name_redirecting_reparse(path: Path) -> bool:
    """Return True only for links/name-surrogate reparses, not cloud placeholders."""

    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    mode = getattr(metadata, "st_mode", 0)
    if stat.S_ISLNK(mode):
        return True
    tag = getattr(metadata, "st_reparse_tag", 0) or 0
    # Windows name-surrogate tags have bit 29 set. OneDrive cloud placeholder
    # tags (for example 0x9000001A) intentionally do not set this bit.
    return bool(tag & 0x20000000)


def _archive_alias_error(project_root: Path, raw_path: str, resolved: Path) -> str | None:
    """Reject name-redirection components and multiply-linked archive files."""

    lexical = project_root.resolve()
    for part in Path(raw_path).parts:
        lexical /= part
        if _is_name_redirecting_reparse(lexical):
            return f"archive path contains a symlink or name-redirecting reparse point: {raw_path}"
    try:
        metadata = os.lstat(resolved)
    except OSError as exc:
        return f"archive evidence metadata is unavailable: {exc}"
    if stat.S_ISREG(getattr(metadata, "st_mode", 0)) and getattr(metadata, "st_nlink", 1) > 1:
        return f"archive evidence is a hardlink alias: {raw_path}"
    return None


def _fixed_archive_contract(approval: dict) -> tuple[tuple[str, ...], str, str] | None:
    prefix = _archive_prefix(approval)
    if prefix is None:
        return None
    subject_type = approval.get("subject_type")
    if subject_type == "STORY":
        return prefix, "01_story/STORY_CONTRACT.md", "STORY_CONTRACT.md"
    if subject_type == "STORYBOARD":
        return prefix, "02_storyboard/storyboard.json", "storyboard.json"
    if subject_type == "LOOKDEV":
        return prefix, "03_lookdev/VISUAL_BIBLE.md", "VISUAL_BIBLE.md"
    if subject_type == "SHOT_STILL" and isinstance(approval.get("subject_id"), str):
        shot_id = approval["subject_id"]
        return prefix, f"05_shots/{shot_id}/shot.json", "shot.json"
    if subject_type == "SOURCE_LIBRARY":
        return prefix, "06_source_library/source_manifest.json", "source_manifest.json"
    return None


def _archive_version_names(project_root: Path, prefix: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """List direct immutable version directories without following redirections."""

    root = project_root.resolve()
    lexical = root
    problems: list[str] = []
    for part in prefix:
        lexical /= part
        if _is_name_redirecting_reparse(lexical):
            return [], [f"archive history root contains a name-redirecting reparse point: {'/'.join(prefix)}"]
    if not lexical.is_dir():
        return [], problems
    versions: list[str] = []
    try:
        children = list(lexical.iterdir())
    except OSError as exc:
        return [], [f"archive history directory is unreadable: {exc}"]
    for child in sorted(children, key=lambda item: item.name.casefold()):
        if re.fullmatch(r"v[0-9]{3,}", child.name) is None:
            continue
        if _is_name_redirecting_reparse(child):
            problems.append(f"archive version is a name-redirecting reparse point: {child.name}")
            continue
        try:
            if child.is_dir():
                versions.append(child.name)
        except OSError as exc:
            problems.append(f"archive version metadata is unavailable for {child.name}: {exc}")
    return versions, problems


def _archive_file_matches(
    project_root: Path,
    raw_path: str,
    expected_hash: str,
) -> tuple[bool, str | None, bool]:
    try:
        resolved = safe_project_path(project_root, raw_path)
    except ValueError as exc:
        return False, str(exc), True
    alias_error = _archive_alias_error(project_root, raw_path, resolved)
    if alias_error:
        return False, alias_error, True
    if not resolved.is_file():
        return False, f"archive evidence file is missing: {raw_path}", False
    try:
        actual_hash = sha256_file(resolved)
    except OSError as exc:
        return False, f"archive evidence is unreadable: {exc}", False
    if actual_hash != expected_hash:
        return False, f"archive evidence bytes/hash are stale: {raw_path}", False
    return True, None, False


def _check_fixed_approval_archives(
    project_root: Path,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    """Bind fixed STORY/STORYBOARD/LOOKDEV approvals to immutable archive copies."""

    claimed_versions: dict[tuple[tuple[str, ...], str], str] = {}
    for approval, approval_path in records["approvals"]:
        status = approval.get("review_status")
        if status not in {
            "USER_REVIEW_REQUIRED",
            "USER_APPROVED",
            "REJECTED",
            "SUPERSEDED",
            "EXCLUDED_FROM_INPUTS",
        }:
            continue
        contract = _fixed_archive_contract(approval)
        if contract is None:
            continue
        prefix, current_authority, archive_filename = contract
        location = canonical_relpath(approval_path, project_root)
        subject_hash = approval.get("subject_sha256")
        evidence = approval.get("evidence") if isinstance(approval.get("evidence"), list) else []
        originals: dict[str, str] = {}
        archive_items: dict[str, str] = {}
        explicit_versions: set[str] = set()
        for item in evidence:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not isinstance(item.get("sha256"), str)
            ):
                continue
            raw_path = Path(item["path"]).as_posix()
            parts = _archive_path_parts(raw_path, prefix)
            if parts is not None:
                archive_items[raw_path] = item["sha256"]
                explicit_versions.add(parts[len(prefix)])
            else:
                previous_hash = originals.get(raw_path)
                if previous_hash is not None and previous_hash != item["sha256"]:
                    errors.append(
                        issue(
                            "ARCHIVE_EVIDENCE_MISSING",
                            f"Conflicting hashes are recorded for fixed-authority evidence path: {raw_path}",
                            path=location,
                        )
                    )
                originals[raw_path] = item["sha256"]

        if not isinstance(subject_hash, str) or originals.get(current_authority) != subject_hash:
            errors.append(
                issue(
                    "ARCHIVE_EVIDENCE_MISSING",
                    f"{approval.get('subject_type')} approval must retain the canonical current authority evidence path/hash",
                    path=location,
                )
            )
            continue

        versions, version_problems = _archive_version_names(project_root, prefix)
        for problem in version_problems:
            errors.append(issue("ARCHIVE_ALIAS_UNSAFE", problem, path=location))

        historical_fixed_decision = (
            status in {"SUPERSEDED", "REJECTED"}
            and isinstance(approval.get("superseded_by_approval_id"), str)
        )
        strict_explicit = not historical_fixed_decision
        if strict_explicit and len(explicit_versions) != 1:
            errors.append(
                issue(
                    "ARCHIVE_VERSION_INVALID",
                    f"Fixed-authority review evidence must explicitly use exactly one immutable version directory: {sorted(explicit_versions)}",
                    path=location,
                )
            )
        candidates = sorted(explicit_versions if explicit_versions else set(versions))
        matching_versions: list[str] = []
        candidate_failures: dict[str, list[str]] = {}
        for version in candidates:
            version_root = "/".join((*prefix, version))
            expected_pairs: dict[str, str] = {}
            for original_path, original_hash in originals.items():
                if original_path == current_authority:
                    counterpart = f"{version_root}/{archive_filename}"
                else:
                    counterpart = f"{version_root}/evidence/{original_path}"
                expected_pairs[counterpart] = original_hash

            failures: list[str] = []
            unsafe_failures: list[str] = []
            canonical_snapshot = f"{version_root}/{archive_filename}"
            if expected_pairs.get(canonical_snapshot) != subject_hash:
                failures.append("canonical authority snapshot hash does not equal subject_sha256")
            for counterpart, expected_hash in expected_pairs.items():
                matched, problem, unsafe = _archive_file_matches(project_root, counterpart, expected_hash)
                if not matched:
                    failures.append(problem or f"archive evidence is invalid: {counterpart}")
                    if unsafe:
                        unsafe_failures.append(problem or f"archive evidence is unsafe: {counterpart}")
                    continue
                if strict_explicit and archive_items.get(counterpart) != expected_hash:
                    failures.append(f"approval evidence omits the exact archive counterpart: {counterpart}")
            if strict_explicit:
                for archive_path, expected_hash in archive_items.items():
                    parts = _archive_path_parts(archive_path, prefix)
                    if parts is None or parts[len(prefix)] != version:
                        continue
                    matched, problem, unsafe = _archive_file_matches(project_root, archive_path, expected_hash)
                    if not matched:
                        failures.append(problem or f"archive evidence is invalid: {archive_path}")
                        if unsafe:
                            unsafe_failures.append(problem or f"archive evidence is unsafe: {archive_path}")
            for problem in sorted(set(unsafe_failures)):
                errors.append(issue("ARCHIVE_ALIAS_UNSAFE", problem, path=location))
            if failures:
                candidate_failures[version] = failures
            else:
                matching_versions.append(version)

        if len(matching_versions) != 1:
            details = [message for version in candidates for message in candidate_failures.get(version, [])]
            message = (
                f"{approval.get('subject_type')} approval archive must contain the canonical authority snapshot "
                "and an exact same-version counterpart for every evidence path"
            )
            errors.append(
                issue(
                    "ARCHIVE_EVIDENCE_MISSING" if not matching_versions else "ARCHIVE_VERSION_INVALID",
                    message,
                    path=location,
                    archive_errors=details,
                )
            )
            continue

        selected_version = matching_versions[0]
        claim_key = (prefix, selected_version)
        approval_id = approval.get("approval_id")
        previous_owner = claimed_versions.get(claim_key)
        if previous_owner is not None and previous_owner != approval_id:
            errors.append(
                issue(
                    "ARCHIVE_VERSION_REUSED",
                    f"Immutable archive {selected_version} is already owned by approval {previous_owner}",
                    path=location,
                    previous_approval_id=previous_owner,
                )
            )
        elif isinstance(approval_id, str):
            claimed_versions[claim_key] = approval_id


def _check_approval_mapping(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    allowed = {
        "STORY": {"STORY"},
        "STORYBOARD": {"STORYBOARD"},
        "LOOKDEV": {"LOOKDEV"},
        "ASSET": {"ASSET_LOCK"},
        "SHOT_STILL": {"SHOT_STILL"},
        "TAKE": {"RAW_VIDEO"},
        "SOURCE_LIBRARY": {"SOURCE_LIBRARY"},
        "TIMELINE": {"EDIT"},
        "DELIVERY": {"FINISH"},
    }
    expected_targets: dict[tuple[str, str], list[tuple[Path, str]]] = {}

    def add_target(subject_type: str, subject_id: object, path: Path | None, digest: object = None) -> None:
        if not isinstance(subject_id, str) or path is None or not path.is_file():
            return
        actual = sha256_file(path)
        if isinstance(digest, str) and digest.casefold() != actual.casefold():
            return
        expected_targets.setdefault((subject_type, subject_id), []).append((path.resolve(), actual))

    for subject_type, subject_id, authority_key, default in (
        ("STORY", "story-contract", "story_contract", "01_story/STORY_CONTRACT.md"),
        ("LOOKDEV", "visual-bible", "visual_bible", "03_lookdev/VISUAL_BIBLE.md"),
    ):
        try:
            target = authority_path(project_root, project, authority_key, default)
        except ValueError:
            continue
        add_target(subject_type, subject_id, target)
    for storyboard, path in records["storyboards"]:
        add_target("STORYBOARD", storyboard.get("storyboard_id"), path)
    for asset, path in records["assets"]:
        lineage = asset.get("lineage") if isinstance(asset.get("lineage"), dict) else {}
        files = asset.get("files") if isinstance(asset.get("files"), dict) else {}
        master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
        add_target("ASSET", asset.get("asset_id"), _safe_record_path(project_root, master.get("path"), path, errors), lineage.get("output_sha256"))
    for take, path in records["takes"]:
        add_target("TAKE", take.get("take_id"), _safe_record_path(project_root, take.get("output_file"), path, errors), take.get("output_sha256"))
    for manifest, path in records["source_manifests"]:
        add_target("SOURCE_LIBRARY", manifest.get("library_id"), path)
    for timeline, path in records["timelines"]:
        add_target("TIMELINE", timeline.get("timeline_id"), path)
    for shot, path in records["shots"]:
        add_target("SHOT_STILL", shot.get("shot_id"), path)
    for delivery, path in records["deliveries"]:
        add_target("DELIVERY", delivery.get("delivery_id"), path)
    for approval, path in records["approvals"]:
        subject_type, gate = approval.get("subject_type"), approval.get("gate")
        if subject_type == "PROJECT_STAGE":
            valid = approval.get("subject_id") == gate
        else:
            valid = gate in allowed.get(subject_type, set())
        if not valid:
            errors.append(issue("APPROVAL_GATE_MISMATCH", f"Approval subject_type {subject_type} cannot approve gate {gate}", path=canonical_relpath(path, project_root)))
        approval_status = approval.get("review_status")
        if approval_status not in {"USER_REVIEW_REQUIRED", "USER_APPROVED"}:
            continue
        if subject_type == "PROJECT_STAGE":
            errors.append(issue("E_UNAPPROVED_INPUT", f"Generic PROJECT_STAGE approval cannot satisfy a v2 gate: {approval.get('approval_id')}", path=canonical_relpath(path, project_root)))
            continue
        subject_hash = approval.get("subject_sha256")
        if not isinstance(subject_hash, str) or len(subject_hash) != 64:
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Review approval lacks a valid subject hash: {approval.get('approval_id')}", path=canonical_relpath(path, project_root)))
            continue
        if approval_status == "USER_APPROVED" and (
            approval.get("decided_by_type") != "USER"
            or not approval.get("user_evidence_reference")
        ):
            errors.append(issue("E_UNAPPROVED_INPUT", f"USER_APPROVED approval lacks explicit user decision: {approval.get('approval_id')}", path=canonical_relpath(path, project_root)))
            continue
        matched = False
        evidence = approval.get("evidence") if isinstance(approval.get("evidence"), list) else []
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval contains incomplete evidence: {approval.get('approval_id')}", path=canonical_relpath(path, project_root)))
                continue
            resolved = _safe_record_path(project_root, item["path"], path, errors)
            if resolved is None:
                continue
            if not resolved.is_file() or sha256_file(resolved) != item["sha256"]:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval evidence bytes mismatch: {item['path']}", path=canonical_relpath(path, project_root)))
            elif item["sha256"] == subject_hash:
                matched = True
        if not matched:
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"No evidence binds subject_sha256 for {approval.get('approval_id')}", path=canonical_relpath(path, project_root)))
        targets = expected_targets.get((subject_type, approval.get("subject_id")), [])
        bound_target = None
        for target_path, target_hash in targets:
            if target_hash != subject_hash:
                continue
            for item in evidence:
                if not isinstance(item, dict) or item.get("sha256") != subject_hash:
                    continue
                resolved = _safe_record_path(project_root, item.get("path"), path, errors)
                if resolved == target_path:
                    bound_target = target_path
                    break
            if bound_target is not None:
                break
        if bound_target is None:
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval subject id/path/hash is not bound to a current concrete authority: {subject_type}/{approval.get('subject_id')}", path=canonical_relpath(path, project_root)))


def _check_prerequisite_evidence_chain(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
    errors: list[dict],
) -> None:
    """Bind every approved artifact to the exact bytes of its immediate prerequisite."""

    approvals = {
        approval.get("approval_id"): (approval, path)
        for approval, path in records["approvals"]
        if isinstance(approval.get("approval_id"), str)
    }

    def has_exact_evidence(approval: dict, approval_path: Path, target: Path | None) -> bool:
        if target is None or not target.is_file():
            return False
        expected_hash = sha256_file(target)
        for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) else []:
            if not isinstance(item, dict) or item.get("sha256") != expected_hash:
                continue
            resolved = _safe_record_path(project_root, item.get("path"), approval_path, errors)
            if resolved == target.resolve():
                return True
        return False

    try:
        story_path = authority_path(project_root, project, "story_contract", "01_story/STORY_CONTRACT.md")
        look_path = authority_path(project_root, project, "visual_bible", "03_lookdev/VISUAL_BIBLE.md")
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        return
    storyboard_item = records["storyboards"][0] if records["storyboards"] else None
    storyboard_path = storyboard_item[1].resolve() if storyboard_item is not None else None
    try:
        source_manifest_path = authority_path(
            project_root,
            project,
            "source_manifest",
            "06_source_library/source_manifest.json",
        )
        current_timeline_path = authority_path(
            project_root,
            project,
            "timeline",
            "07_edit/timeline.json",
        )
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        source_manifest_path = None
        current_timeline_path = None

    if storyboard_item is not None:
        storyboard, record_path = storyboard_item
        board_approvals = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="STORYBOARD",
            subject_id=storyboard.get("storyboard_id"),
            gate="STORYBOARD",
            target_path=record_path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        for approval, approval_path in board_approvals:
            if not has_exact_evidence(approval, approval_path, story_path):
                errors.append(
                    issue(
                        "E_APPROVAL_HASH_MISMATCH",
                        "Storyboard approval evidence must include current story contract path and hash",
                        path=canonical_relpath(record_path, project_root),
                    )
                )

    for approval, approval_path in records["approvals"]:
        if (
            approval.get("review_status") not in REVIEW_READY_APPROVAL_STATUSES
            or approval.get("subject_type") != "LOOKDEV"
            or approval.get("superseded_by_approval_id")
        ):
            continue
        if not has_exact_evidence(approval, approval_path, storyboard_path):
            errors.append(
                issue(
                    "E_APPROVAL_HASH_MISMATCH",
                    "Lookdev approval evidence must include current storyboard path and hash",
                    path=canonical_relpath(approval_path, project_root),
                )
            )

    for asset, record_path in records["assets"]:
        target_path = _production_subject_path(project_root, "assets", asset, record_path)
        if target_path is None:
            continue
        candidates = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="ASSET",
            subject_id=asset.get("asset_id"),
            gate="ASSET_LOCK",
            target_path=target_path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        if not candidates:
            continue
        for approval, approval_path in candidates:
            if not has_exact_evidence(approval, approval_path, look_path):
                errors.append(
                    issue(
                        "E_APPROVAL_HASH_MISMATCH",
                        "Asset approval evidence must include current visual bible path and hash",
                        path=canonical_relpath(record_path, project_root),
                    )
                )

    for timeline, record_path in records["timelines"]:
        if (
            current_timeline_path is None
            or record_path.resolve() != current_timeline_path.resolve()
        ):
            continue
        candidates = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="TIMELINE",
            subject_id=timeline.get("timeline_id"),
            gate="EDIT",
            target_path=record_path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        for approval, approval_path in candidates:
            if not has_exact_evidence(approval, approval_path, source_manifest_path):
                errors.append(
                    issue(
                        "E_APPROVAL_HASH_MISMATCH",
                        "Timeline approval evidence must include current source manifest path and hash",
                        path=canonical_relpath(record_path, project_root),
                    )
                )

    shots = {
        shot.get("shot_id"): (shot, path.resolve())
        for shot, path in records["shots"]
        if isinstance(shot.get("shot_id"), str)
    }
    for take, record_path in records["takes"]:
        target_path = _production_subject_path(project_root, "takes", take, record_path)
        if target_path is None:
            continue
        candidates = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="TAKE",
            subject_id=take.get("take_id"),
            gate="RAW_VIDEO",
            target_path=target_path,
            statuses=REVIEW_READY_APPROVAL_STATUSES,
        )
        if not candidates:
            continue
        shot_item = shots.get(take.get("shot_id"))
        if shot_item is None:
            continue
        shot, shot_path = shot_item
        expected_hash = sha256_file(shot_path) if shot_path.is_file() else None
        bound = False
        for item in take.get("input_hashes", []) if isinstance(take.get("input_hashes"), list) else []:
            if not isinstance(item, dict) or item.get("sha256") != expected_hash:
                continue
            resolved = _safe_record_path(project_root, item.get("path"), record_path, errors)
            if resolved == shot_path:
                bound = True
                break
        shot_approvals = _bound_content_approvals(
            project_root,
            project,
            records,
            subject_type="SHOT_STILL",
            subject_id=shot.get("shot_id"),
            gate="SHOT_STILL",
            target_path=shot_path,
            statuses={"USER_APPROVED"},
        )
        approval_has_shot = all(
            has_exact_evidence(approval, approval_path, shot_path)
            for approval, approval_path in candidates
        )
        if len(shot_approvals) != 1 or not bound or not approval_has_shot:
            errors.append(
                issue(
                    "E_APPROVAL_HASH_MISMATCH",
                    "Review-ready take must bind current approved shot.json in input_hashes and approval evidence",
                    path=canonical_relpath(record_path, project_root),
                )
                )


def _run_semantic_check(
    errors: list[dict],
    check,
    *args,
) -> None:
    """Run one semantic phase without exposing malformed-record tracebacks."""

    try:
        check(*args)
    except Exception as exc:
        errors.append(
            issue(
                "VALIDATION_RUNTIME_ERROR",
                f"{check.__name__} rejected malformed record data "
                f"({type(exc).__name__}): {exc}",
            )
        )


def _candidate_semantic_checks(
    project_root: Path,
    project: dict,
    records: dict[str, list[tuple[dict, Path]]],
) -> list[dict]:
    errors: list[dict] = []
    for check, args in (
        (_check_unique_ids, (project_root, records, errors)),
        (_check_project_ids, (project_root, project, records, errors)),
        (_check_references, (project_root, project, records, errors)),
        (_check_shot_dependency_snapshots, (project_root, project, records, errors)),
        (_check_still_evidence, (project_root, project, records, errors)),
        (_check_deliveries, (project_root, project, records, errors)),
        (_check_approval_gates, (project_root, project, records, errors)),
        (_check_ids_and_lineage, (project_root, records, errors)),
        (_check_storyboards, (project_root, project, records, errors)),
        (_check_remote_evidence, (project_root, records, errors)),
        (_check_local_processing_hashes, (project_root, project, records, errors)),
        (_check_source_and_timeline, (project_root, project, records, errors)),
        (_check_timeline_revisions, (project_root, project, records, errors)),
        (_check_approval_mapping, (project_root, project, records, errors)),
        (_check_approval_replacement_graph, (project_root, records, errors)),
        (_check_prerequisite_evidence_chain, (project_root, project, records, errors)),
    ):
        _run_semantic_check(errors, check, *args)
    return errors


def _planned_fixed_archive_errors(
    project_root: Path,
    approval: dict,
    approval_path: Path,
) -> list[dict]:
    subject_type = approval.get("subject_type")
    if subject_type not in {"STORY", "STORYBOARD", "LOOKDEV", "SHOT_STILL", "SOURCE_LIBRARY"}:
        return []
    subject_id = approval.get("subject_id")
    prefixes = {
        "STORY": ("01_story/history/story-contract", "STORY_CONTRACT.md"),
        "STORYBOARD": (f"02_storyboard/history/{subject_id}", "storyboard.json"),
        "LOOKDEV": ("03_lookdev/history/visual-bible", "VISUAL_BIBLE.md"),
        "SHOT_STILL": (f"05_shots/{subject_id}/history", "shot.json"),
        "SOURCE_LIBRARY": (f"06_source_library/history/{subject_id}", "source_manifest.json"),
    }
    current_authorities = {
        "STORY": "01_story/STORY_CONTRACT.md",
        "STORYBOARD": "02_storyboard/storyboard.json",
        "LOOKDEV": "03_lookdev/VISUAL_BIBLE.md",
        "SHOT_STILL": f"05_shots/{subject_id}/shot.json",
        "SOURCE_LIBRARY": "06_source_library/source_manifest.json",
    }
    prefix, authority_name = prefixes[subject_type]
    current_authority = current_authorities[subject_type]
    evidence = [item for item in approval.get("evidence", []) if isinstance(item, dict)]
    versions: set[str] = set()
    archive_by_path: dict[str, str] = {}
    current_items: list[tuple[str, str]] = []
    for item in evidence:
        raw_path, digest = item.get("path"), item.get("sha256")
        if not isinstance(raw_path, str) or not isinstance(digest, str):
            continue
        normalized = raw_path.replace("\\", "/")
        match = re.fullmatch(rf"{re.escape(prefix)}/(v[0-9]{{3,}})/(.*)", normalized)
        if match:
            versions.add(match.group(1))
            archive_by_path[f"{match.group(1)}/{match.group(2)}"] = digest
        else:
            current_items.append((normalized, digest))
    errors: list[dict] = []
    if len(versions) != 1:
        return [
            issue(
                "ARCHIVE_VERSION_INVALID",
                "Review candidate must declare exactly one fixed-authority archive version",
                path=canonical_relpath(approval_path, project_root),
            )
        ]
    version = next(iter(versions))
    subject_hash = approval.get("subject_sha256")
    if archive_by_path.get(f"{version}/{authority_name}") != subject_hash:
        errors.append(issue("ARCHIVE_EVIDENCE_MISSING", "Review candidate lacks its canonical authority archive mirror", path=canonical_relpath(approval_path, project_root)))
    current_hashes = [digest for path, digest in current_items if path == current_authority]
    if current_hashes != [subject_hash]:
        errors.append(
            issue(
                "E_APPROVAL_HASH_MISMATCH",
                f"Review candidate must bind the exact current authority path: {current_authority}",
                path=canonical_relpath(approval_path, project_root),
            )
        )
    for raw_path, digest in current_items:
        if raw_path == current_authority:
            continue
        expected = f"{version}/evidence/{raw_path}"
        if archive_by_path.get(expected) != digest:
            errors.append(
                issue(
                    "ARCHIVE_EVIDENCE_MISSING",
                    f"Review candidate lacks an exact archive counterpart for {raw_path}",
                    path=canonical_relpath(approval_path, project_root),
                )
            )
    return errors


def validate_review_candidate(
    project_root: str | Path,
    subject_type: str,
    subject_id: str,
    proposed_approval: dict,
) -> dict:
    """Validate one in-memory central review package without publishing it."""

    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    checked: set[str] = set()
    try:
        project = read_json(root / "project.json")
        if not isinstance(project, dict):
            raise ValueError("project.json must contain an object")
        records = _collect_records(root, project, errors, checked)
        approvals_root = resolve_project_path(root, project, "approvals", "09_approvals")
        approval_id = proposed_approval.get("approval_id")
        if not isinstance(approval_id, str):
            raise ValueError("Proposed approval_id is required")
        approval_path = approvals_root / f"{approval_id}.json"
        existing = [
            (approval, path)
            for approval, path in records["approvals"]
            if approval.get("approval_id") == approval_id
        ]
        if len(existing) > 1:
            errors.append(issue("DUPLICATE_ID", f"Approval ID is not unique: {approval_id}", path=canonical_relpath(approval_path, root)))
        elif existing and existing[0][1].resolve() != approval_path.resolve():
            errors.append(
                issue(
                    "DUPLICATE_ID",
                    f"Approval ID exists at a non-canonical path: {approval_id}",
                    path=canonical_relpath(existing[0][1], root),
                )
            )
        if (
            proposed_approval.get("project_id") != project.get("project_id")
            or proposed_approval.get("subject_type") != subject_type
            or proposed_approval.get("subject_id") != subject_id
            or proposed_approval.get("gate") != next((gate for gate, kind in GATE_SUBJECT_TYPES.items() if kind == subject_type), None)
        ):
            errors.append(issue("APPROVAL_GATE_MISMATCH", "Proposed review package does not match the requested project/type/id/gate", path=canonical_relpath(approval_path, root)))

        schema_dir = resolve_project_path(root, project, "schemas", "00_schemas")
        schema_trusted = _validate_schema_snapshot_trust(
            root, project, schema_dir, errors, checked
        )
        errors.extend(_planned_fixed_archive_errors(root, proposed_approval, approval_path))

        # Future archive mirrors are intentionally absent during dry-run.  The
        # semantic pass sees only evidence that already exists; archive pair
        # structure and hashes are checked separately above.
        semantic_approval = dict(proposed_approval)
        existing_evidence: list[dict] = []
        for item in proposed_approval.get("evidence", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            try:
                evidence_path = safe_project_path(root, item["path"])
            except ValueError:
                continue
            if evidence_path.is_file():
                existing_evidence.append(item)
        semantic_approval["evidence"] = existing_evidence

        baseline_errors: list[dict] = []
        if schema_trusted:
            _validate_schemas(
                root,
                schema_dir,
                _schema_targets(project, root / "project.json", records),
                baseline_errors,
                [],
            )
        baseline_errors.extend(_candidate_semantic_checks(root, project, records))
        _check_fixed_approval_archives(root, records, baseline_errors)
        errors.extend(baseline_errors)
        if not baseline_errors:
            candidate_records = {key: list(value) for key, value in records.items()}
            candidate_records["approvals"] = [
                (approval, path)
                for approval, path in candidate_records["approvals"]
                if approval.get("approval_id") != approval_id
            ]
            candidate_records["approvals"].append((proposed_approval, approval_path))
            if schema_trusted:
                _validate_schemas(
                    root,
                    schema_dir,
                    _schema_targets(project, root / "project.json", candidate_records),
                    errors,
                    [],
                )
            semantic_records = {key: list(value) for key, value in candidate_records.items()}
            semantic_records["approvals"] = [
                (semantic_approval if approval.get("approval_id") == approval_id else approval, path)
                for approval, path in semantic_records["approvals"]
            ]
            errors.extend(_candidate_semantic_checks(root, project, semantic_records))
    except Exception as exc:
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", str(exc)))
    return {
        **OFFLINE_VERIFICATION,
        "ok": not errors,
        "errors": errors,
        "subject_type": subject_type,
        "subject_id": subject_id,
    }


def _validate_project_impl(
    project_root: str | Path, *, schema_dir: str | Path | None = None
) -> dict:
    """Return a machine-readable validation report without changing the project."""

    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    warnings: list[dict] = []
    checked: set[str] = set()
    project_path = root / "project.json"
    if not root.is_dir():
        return {
            **OFFLINE_VERIFICATION,
            "ok": False,
            "errors": [issue("PROJECT_NOT_FOUND", f"Project directory not found: {root}")],
            "warnings": [],
            "checked_files": [],
        }
    if not project_path.exists():
        return {
            **OFFLINE_VERIFICATION,
            "ok": False,
            "errors": [issue("PROJECT_FILE_MISSING", "project.json is required")],
            "warnings": [],
            "checked_files": [],
        }

    project = _load(project_path, root, errors, checked)
    if project is not None and not isinstance(project, dict):
        errors.append(issue("INVALID_PROJECT", "project.json must contain an object", path="project.json"))
        project = None
    try:
        records = _collect_records(root, project or {}, errors, checked)
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path="project.json"))
        records = {key: [] for key in ("assets", "shots", "takes", "approvals", "sources", "source_manifests", "storyboards", "timelines", "deliveries")}
    if schema_dir is not None:
        selected_schema_dir = Path(schema_dir).expanduser().resolve()
        schema_source = "override"
    else:
        try:
            project_schema_dir = resolve_project_path(root, project or {}, "schemas", "00_schemas")
        except ValueError:
            project_schema_dir = root / "00_schemas"
        paths_record = project.get("paths") if isinstance(project, dict) and isinstance(project.get("paths"), dict) else {}
        declares_snapshot = (
            isinstance(project, dict)
            and project.get("schema_version") == "2.0.0"
            and isinstance(paths_record.get("schemas"), str)
        )
        if declares_snapshot:
            selected_schema_dir = project_schema_dir
            schema_source = "project_snapshot"
            if not project_schema_dir.is_dir():
                errors.append(issue("SCHEMA_SNAPSHOT_MISSING", f"Declared project schema snapshot is missing: {project_schema_dir}", path="project.json"))
        elif project_schema_dir.is_dir():
            selected_schema_dir = project_schema_dir
            schema_source = "project_snapshot"
        else:
            selected_schema_dir = Path(__file__).resolve().parents[1] / "schemas"
            schema_source = "skill_fallback"
    schema_trusted = schema_source != "project_snapshot"
    if schema_source == "project_snapshot" and isinstance(project, dict):
        schema_trusted = _validate_schema_snapshot_trust(
            root, project, selected_schema_dir, errors, checked
        )
    if schema_trusted:
        _validate_schemas(
            root,
            selected_schema_dir,
            _schema_targets(project, project_path, records),
            errors,
            warnings,
        )
    _run_semantic_check(errors, _check_unique_ids, root, records, errors)
    _run_semantic_check(errors, _check_statuses, root, project, records, errors)
    if isinstance(project, dict):
        _run_semantic_check(errors, _check_project_ids, root, project, records, errors)
        _run_semantic_check(errors, _check_active_stage_approvals, root, project, records, errors)
        _run_semantic_check(errors, _check_authority_targets, root, project, errors)
    _run_semantic_check(errors, _check_references, root, project or {}, records, errors)
    _run_semantic_check(errors, _check_shot_dependency_snapshots, root, project or {}, records, errors)
    _run_semantic_check(errors, _check_still_evidence, root, project or {}, records, errors)
    _run_semantic_check(errors, _check_deliveries, root, project or {}, records, errors)
    _run_semantic_check(errors, _check_approval_gates, root, project or {}, records, errors)
    if isinstance(project, dict):
        _run_semantic_check(errors, _check_completion, project, records, errors)
        _run_semantic_check(errors, _check_paths, root, project, records, errors)
    for check, args in (
        (_check_ids_and_lineage, (root, records, errors)),
        (_check_storyboards, (root, project or {}, records, errors)),
        (_check_remote_evidence, (root, records, errors)),
        (_check_local_processing_hashes, (root, project or {}, records, errors)),
        (_check_source_and_timeline, (root, project or {}, records, errors)),
        (_check_timeline_revisions, (root, project or {}, records, errors)),
        (_check_approval_mapping, (root, project or {}, records, errors)),
        (_check_approval_replacement_graph, (root, records, errors)),
        (_check_decision_receipts, (root, project or {}, records, errors)),
        (_check_fixed_approval_archives, (root, records, errors)),
        (_check_prerequisite_evidence_chain, (root, project or {}, records, errors)),
    ):
        _run_semantic_check(errors, check, *args)
    return {
        **OFFLINE_VERIFICATION,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked_files": sorted(checked),
        "schema_source": schema_source,
        "schema_dir": str(selected_schema_dir),
    }


def validate_project(
    project_root: str | Path, *, schema_dir: str | Path | None = None
) -> dict:
    """Fail-closed public validation boundary for all untrusted project data."""

    try:
        return _validate_project_impl(project_root, schema_dir=schema_dir)
    except Exception as exc:
        return {
            **OFFLINE_VERIFICATION,
            "ok": False,
            "errors": [
                issue(
                    "VALIDATION_RUNTIME_ERROR",
                    f"Project validation rejected malformed data ({type(exc).__name__}): {exc}",
                )
            ],
            "warnings": [],
            "checked_files": [],
            "schema_source": "unavailable",
            "schema_dir": str(schema_dir) if schema_dir is not None else None,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--schema-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_project(args.project_root, schema_dir=args.schema_dir)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["ok"] else "FAIL")
        for category in ("errors", "warnings"):
            for item in result[category]:
                prefix = "ERROR" if category == "errors" else "WARN"
                location = f" [{item['path']}]" if item.get("path") else ""
                print(f"{prefix} {item['code']}{location}: {item['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
