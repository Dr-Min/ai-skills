#!/usr/bin/env python3
"""Prepare a central, evidence-bound Cinema Studio user-review request."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _cinema_common import (
    authority_path,
    canonical_relpath,
    discover_approval_paths,
    discover_asset_paths,
    discover_take_paths,
    issue,
    project_path,
    read_json,
    read_project,
    safe_project_path,
    sha256_file,
)
from validate_project import _is_name_redirecting_reparse, validate_review_candidate


OFFLINE = {"verification_scope": "OFFLINE_RECORD_CONSISTENCY", "remote_truth_verified": False}
SUBJECT_GATES = {
    "STORY": "STORY", "STORYBOARD": "STORYBOARD", "LOOKDEV": "LOOKDEV", "ASSET": "ASSET_LOCK",
    "SHOT_STILL": "SHOT_STILL", "SOURCE_LIBRARY": "SOURCE_LIBRARY",
    "TAKE": "RAW_VIDEO", "TIMELINE": "EDIT", "DELIVERY": "FINISH",
}
FIXED_SUBJECTS = frozenset({"STORY", "STORYBOARD", "LOOKDEV", "SHOT_STILL", "SOURCE_LIBRARY"})


def _result(*, allowed: bool, errors: list[dict], **values: object) -> dict:
    return {**OFFLINE, "allowed": allowed, "review_prepared": False, "gate_activated": False, "errors": errors, **values}


def _lexical_project_path(root: Path, raw_path: str) -> Path:
    """Validate containment while retaining the caller's lexical path for alias checks."""
    safe_project_path(root, raw_path)
    return root.resolve().joinpath(*Path(raw_path).parts)


def _assert_safe_write_target(root: Path, target: Path) -> None:
    """Reject aliases before any create can traverse an in-project redirect."""
    try:
        relative = target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Write target escapes project root: {target}") from exc
    current = root.resolve()
    for part in relative.parts:
        current /= part
        if not current.exists() and not current.is_symlink():
            break
        if _is_name_redirecting_reparse(current):
            raise ValueError(f"Write target contains a symlink or name-redirecting reparse point: {current}")
    if target.exists() or target.is_symlink():
        metadata = os.lstat(target)
        if _is_name_redirecting_reparse(target) or getattr(metadata, "st_nlink", 1) > 1:
            raise ValueError(f"Write target is an unsafe preseeded alias: {target}")


def _safe_bytes_copy(root: Path, source: Path, destination: Path) -> None:
    """Create a new, fsynced copy; never replace or link mutable authority bytes."""
    _assert_safe_write_target(root, destination)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite immutable path: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_write_target(root, destination)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
            while block := input_handle.read(1024 * 1024):
                output_handle.write(block)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        # link() is atomic create-if-absent and cannot overwrite a concurrent writer.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_create_json(root: Path, path: Path, payload: dict) -> None:
    _assert_safe_write_target(root, path)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite approval: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_safe_write_target(root, path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cleanup_unpublished_archive(
    root: Path,
    approval_path: Path,
    version_root: Path | None,
    created_files: list[tuple[Path, str]],
) -> None:
    """Remove only unchanged archive bytes created by this failed publication."""

    if approval_path.exists() or version_root is None:
        return
    resolved_root = root.resolve()
    try:
        resolved_version = version_root.resolve()
        resolved_version.relative_to(resolved_root)
    except (OSError, ValueError):
        return
    for destination, created_hash in reversed(created_files):
        try:
            resolved_destination = destination.resolve()
            resolved_destination.relative_to(resolved_version)
            _assert_safe_write_target(root, destination)
            if destination.is_file() and sha256_file(destination) == created_hash:
                destination.unlink()
        except (OSError, ValueError):
            continue
    directories = sorted(
        {
            parent
            for destination, _ in created_files
            for parent in destination.parents
            if parent == version_root or version_root in parent.parents
        },
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.resolve().relative_to(resolved_version)
            if _is_name_redirecting_reparse(directory):
                continue
            directory.rmdir()
        except (OSError, ValueError):
            continue


def _authority(root: Path, project: dict, subject_type: str, subject_id: str) -> tuple[Path, dict | None]:
    if subject_type == "STORY":
        if subject_id != "story-contract":
            raise ValueError("STORY subject_id must be story-contract")
        return authority_path(root, project, "story_contract", "01_story/STORY_CONTRACT.md"), None
    if subject_type == "STORYBOARD":
        path = authority_path(root, project, "storyboard", "02_storyboard/storyboard.json")
    elif subject_type == "LOOKDEV":
        if subject_id != "visual-bible":
            raise ValueError("LOOKDEV subject_id must be visual-bible")
        return authority_path(root, project, "visual_bible", "03_lookdev/VISUAL_BIBLE.md"), None
    elif subject_type == "SHOT_STILL":
        shots = project_path(root, project, "shots", "05_shots")
        path = safe_project_path(root, canonical_relpath(shots / subject_id / "shot.json", root))
    elif subject_type == "ASSET":
        matches = []
        for candidate in discover_asset_paths(root, project):
            payload = read_json(candidate)
            if isinstance(payload, dict) and payload.get("asset_id") == subject_id:
                matches.append((payload, candidate))
        if len(matches) != 1:
            raise ValueError("ASSET subject must resolve to exactly one asset record")
        record, _ = matches[0]
        master = record.get("files", {}).get("immutable_master", {}) if isinstance(record.get("files"), dict) else {}
        if not isinstance(master, dict) or not isinstance(master.get("path"), str):
            raise ValueError("ASSET immutable master is missing")
        path = safe_project_path(root, master["path"])
        if not path.is_file() or sha256_file(path) != master.get("sha256"):
            raise ValueError("ASSET immutable master bytes mismatch")
        return path, record
    elif subject_type == "TAKE":
        matches = []
        for candidate in discover_take_paths(root, project):
            payload = read_json(candidate)
            if isinstance(payload, dict) and payload.get("take_id") == subject_id:
                matches.append((payload, candidate))
        if len(matches) != 1:
            raise ValueError("TAKE subject must resolve to exactly one take record")
        record, _ = matches[0]
        if not isinstance(record.get("output_file"), str):
            raise ValueError("TAKE output file is missing")
        path = safe_project_path(root, record["output_file"])
        if not path.is_file() or sha256_file(path) != record.get("output_sha256"):
            raise ValueError("TAKE output bytes mismatch")
        return path, record
    elif subject_type == "SOURCE_LIBRARY":
        path = authority_path(root, project, "source_manifest", "06_source_library/source_manifest.json")
    elif subject_type == "TIMELINE":
        path = authority_path(root, project, "timeline", "07_edit/timeline.json")
    elif subject_type == "DELIVERY":
        path = authority_path(root, project, "delivery_record", "08_delivery/delivery.json")
    else:
        raise ValueError(f"Unsupported subject_type: {subject_type}")
    if not path.is_file():
        raise ValueError("Current content authority candidate does not exist")
    record = read_json(path)
    key = {"STORYBOARD": "storyboard_id", "SHOT_STILL": "shot_id", "SOURCE_LIBRARY": "library_id", "TIMELINE": "timeline_id", "DELIVERY": "delivery_id"}[subject_type]
    if not isinstance(record, dict) or record.get(key) != subject_id:
        raise ValueError(f"Current authority does not bind {subject_type}/{subject_id}")
    if record.get("project_id") != project.get("project_id"):
        raise ValueError("Current authority belongs to another project")
    if subject_type == "SOURCE_LIBRARY" and record.get("lock_status") != "SOURCE_LOCKED":
        raise ValueError("SOURCE_LIBRARY requires a SOURCE_LOCKED current candidate")
    if subject_type == "TIMELINE" and record.get("lock_status") != "PICTURE_LOCKED":
        raise ValueError("TIMELINE requires a PICTURE_LOCKED current candidate")
    return path, record


def _record_path(root: Path, project: dict, subject_type: str, subject_id: str) -> Path:
    discover = discover_asset_paths if subject_type == "ASSET" else discover_take_paths
    key = "asset_id" if subject_type == "ASSET" else "take_id"
    paths = [path for path in discover(root, project) if isinstance(read_json(path), dict) and read_json(path).get(key) == subject_id]
    if len(paths) != 1:
        raise ValueError(f"{subject_type} record is not unique")
    return paths[0]


def _supporting_evidence(root: Path, project: dict, subject_type: str, record: dict | None, supplied: tuple[str, ...]) -> list[tuple[Path, str]]:
    """Collect mandatory visual/QA proof which must travel with the central review."""
    paths: list[tuple[Path, str]] = []

    def add(path: Path, claim: str, declared_hash: str | None = None) -> None:
        if not path.is_file():
            raise ValueError(f"Supporting evidence does not exist: {canonical_relpath(path, root)}")
        actual = sha256_file(path)
        if declared_hash is not None and actual != declared_hash:
            raise ValueError("Supporting evidence hash does not match its content authority")
        if path.resolve() not in {item[0].resolve() for item in paths}:
            paths.append((path, claim))

    if subject_type == "STORYBOARD" and record is not None:
        dependency = record.get("story_dependency")
        if not isinstance(dependency, dict) or not isinstance(dependency.get("path"), str):
            raise ValueError("Storyboard story_dependency is incomplete")
        add(safe_project_path(root, dependency["path"]), "Storyboard story dependency", dependency.get("sha256"))
        scenes = record.get("scenes")
        if not isinstance(scenes, list):
            raise ValueError("Storyboard scene panel evidence is incomplete")
        for scene in scenes:
            if not isinstance(scene, dict) or not isinstance(scene.get("panels"), list):
                raise ValueError("Storyboard scene panel evidence is incomplete")
            for panel in scene["panels"]:
                if not isinstance(panel, dict) or not isinstance(panel.get("image_file"), str):
                    raise ValueError("Storyboard panel image evidence is incomplete")
                add(safe_project_path(root, panel["image_file"]), "Storyboard panel pixel evidence", panel.get("image_sha256"))
    if subject_type == "LOOKDEV":
        storyboard = authority_path(root, project, "storyboard", "02_storyboard/storyboard.json")
        if not storyboard.is_file():
            raise ValueError("LOOKDEV requires the current storyboard authority")
        board = read_json(storyboard)
        if not isinstance(board, dict) or not isinstance(board.get("storyboard_id"), str):
            raise ValueError("LOOKDEV current storyboard is invalid")
        add(storyboard, "Current storyboard authority")
        for path, claim in _supporting_evidence(root, project, "STORYBOARD", board, ()):
            add(path, claim)
    if subject_type == "SHOT_STILL" and record is not None:
        evidence = record.get("still_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("SHOT_STILL requires nonempty still_evidence")
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("Shot still evidence is incomplete")
            image = safe_project_path(root, item["path"])
            add(image, f"Visible shot still: {item.get('role', 'STILL')}", item.get("sha256"))
        spatial = record.get("spatial") if isinstance(record.get("spatial"), dict) else {}
        control_packet = spatial.get("control_packet")
        if control_packet is not None:
            if not isinstance(control_packet, dict) or not isinstance(control_packet.get("path"), str):
                raise ValueError("Shot spatial control_packet is incomplete")
            packet_path = safe_project_path(root, control_packet["path"])
            add(packet_path, "Spatial control packet", control_packet.get("sha256"))
            packet = read_json(packet_path)
            if (
                not isinstance(packet, dict)
                or packet.get("shot_id") != record.get("shot_id")
                or packet.get("structural_scope_only") is not True
            ):
                raise ValueError("Spatial control packet does not bind this shot as structural-only evidence")
            outputs = packet.get("outputs")
            if not isinstance(outputs, dict):
                raise ValueError("Spatial control packet outputs are incomplete")
            for role in ("review_map", "clean_map"):
                item = outputs.get(role)
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    raise ValueError(f"Spatial control packet {role} evidence is incomplete")
                add(
                    safe_project_path(root, item["path"]),
                    f"Spatial control {role}",
                    item.get("sha256"),
                )
    if subject_type == "DELIVERY" and record is not None:
        export = record.get("export") if isinstance(record.get("export"), dict) else {}
        if not isinstance(export.get("path"), str):
            raise ValueError("DELIVERY requires export evidence")
        output = safe_project_path(root, export["path"])
        add(output, "Final delivery export bytes", export.get("sha256"))
        qa = record.get("qa") if isinstance(record.get("qa"), dict) else {}
        for check in qa.values():
            if not isinstance(check, dict):
                continue
            for item in check.get("evidence", []) if isinstance(check.get("evidence"), list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    raise ValueError("Delivery QA evidence is incomplete")
                evidence = safe_project_path(root, item["path"])
                add(evidence, "Delivery QA evidence", item.get("sha256"))
        if len(paths) < 2:
            raise ValueError("DELIVERY requires export and QA evidence")
    if subject_type == "SOURCE_LIBRARY" and record is not None:
        sources = record.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("SOURCE_LIBRARY requires admitted sources")
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                raise ValueError("Source library evidence is incomplete")
            add(safe_project_path(root, source["path"]), "Admitted source media", source.get("sha256"))
    if subject_type == "ASSET" and record is not None:
        record_path = _record_path(root, project, subject_type, record["asset_id"])
        add(record_path, "Asset authority record")
        look = authority_path(root, project, "visual_bible", "03_lookdev/VISUAL_BIBLE.md")
        if not look.is_file():
            raise ValueError("ASSET requires current lookdev authority")
        add(look, "Current lookdev authority")
    if subject_type == "TAKE" and record is not None:
        record_path = _record_path(root, project, subject_type, record["take_id"])
        add(record_path, "Take authority record")
        shot_id = record.get("shot_id")
        if not isinstance(shot_id, str):
            raise ValueError("TAKE requires its current shot authority")
        shot = safe_project_path(root, f"05_shots/{shot_id}/shot.json")
        add(shot, "Current shot authority")
        for item in record.get("input_hashes", []) if isinstance(record.get("input_hashes"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("TAKE input hash is incomplete")
            add(safe_project_path(root, item["path"]), "Take input authority", item.get("sha256"))
    if subject_type == "TIMELINE":
        source_manifest = authority_path(root, project, "source_manifest", "06_source_library/source_manifest.json")
        if not source_manifest.is_file():
            raise ValueError("TIMELINE requires the current source manifest")
        add(source_manifest, "Current source library authority")
    for raw_path in supplied:
        if not isinstance(raw_path, str):
            raise ValueError("Supporting evidence path is invalid")
        add(safe_project_path(root, raw_path), "Caller-supplied review evidence")
    return paths


def _validate_approval_candidate(root: Path, project: dict, payload: dict) -> None:
    """Validate only against the project's trusted snapshot, never a fallback schema."""
    snapshot = project_path(root, project, "schemas", "00_schemas")
    trusted = Path(__file__).resolve().parents[1] / "schemas"
    snapshot_manifest = snapshot / "schema-manifest.json"
    trusted_manifest = trusted / "schema-manifest.json"
    snapshot_schema = snapshot / "approval.schema.json"
    trusted_schema = trusted / "approval.schema.json"
    if not all(path.is_file() for path in (snapshot_manifest, trusted_manifest, snapshot_schema, trusted_schema)):
        raise ValueError("Trusted project approval schema snapshot is missing")
    if sha256_file(snapshot_manifest) != sha256_file(trusted_manifest) or sha256_file(snapshot_schema) != sha256_file(trusted_schema):
        raise ValueError("Project approval schema snapshot is not trusted")
    try:
        import jsonschema
        schema = read_json(snapshot_schema)
        validator = jsonschema.validators.validator_for(schema)
        validator.check_schema(schema)
        errors = sorted(validator(schema).iter_errors(payload), key=lambda item: list(item.absolute_path))
    except ImportError as exc:
        raise ValueError("jsonschema is required for trusted approval validation") from exc
    if errors:
        raise ValueError(f"Approval candidate fails trusted schema: {errors[0].message}")


def _archive_plan(root: Path, subject_type: str, subject_id: str, authority: Path, evidence: list[tuple[Path, str]]) -> tuple[str, list[tuple[Path, Path, str]]]:
    authority_rel = canonical_relpath(authority, root)
    if subject_type == "STORY":
        prefix, filename = "01_story/history/story-contract", "STORY_CONTRACT.md"
    elif subject_type == "STORYBOARD":
        prefix, filename = f"02_storyboard/history/{subject_id}", "storyboard.json"
    elif subject_type == "LOOKDEV":
        prefix, filename = "03_lookdev/history/visual-bible", "VISUAL_BIBLE.md"
    elif subject_type == "SHOT_STILL":
        prefix, filename = f"05_shots/{subject_id}/history", "shot.json"
    else:
        prefix, filename = f"06_source_library/history/{subject_id}", "source_manifest.json"
    archive_root = _lexical_project_path(root, prefix)
    versions = []
    if archive_root.is_dir():
        for item in archive_root.iterdir():
            match = re.fullmatch(r"v([0-9]{3,})", item.name)
            if match and item.is_dir():
                versions.append(int(match.group(1)))
    version = f"v{(max(versions, default=0) + 1):03d}"
    base = _lexical_project_path(root, f"{prefix}/{version}")
    copies = [(authority, base / filename, "Current content authority")]
    for source, claim in evidence:
        if source.resolve() == authority.resolve():
            continue
        copies.append((source, base / "evidence" / canonical_relpath(source, root), claim))
    return version, copies


def _next_approval_id(root: Path, project: dict, gate: str) -> tuple[str, Path]:
    paths = project.get("paths") if isinstance(project.get("paths"), dict) else {}
    approvals_raw = paths.get("approvals", "09_approvals")
    if not isinstance(approvals_raw, str):
        raise ValueError("Project approvals path is invalid")
    approvals = _lexical_project_path(root, approvals_raw)
    used: list[int] = []
    for candidate in discover_approval_paths(root, project):
        try:
            approval = read_json(candidate)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Central approval record is unreadable: {candidate}") from exc
        if not isinstance(approval, dict):
            raise ValueError(f"Central approval record must contain an object: {candidate}")
        match = re.fullmatch(rf"APR_{re.escape(gate)}_(\d{{3,4}})", str(approval.get("approval_id", "")))
        if match:
            used.append(int(match.group(1)))
    number = max(used, default=0) + 1
    approval_id = f"APR_{gate}_{number:04d}"
    return approval_id, _lexical_project_path(root, f"{approvals_raw}/{approval_id}.json")


def _has_pending_subject(root: Path, project: dict, subject_type: str, subject_id: str) -> bool:
    for path in discover_approval_paths(root, project):
        try:
            approval = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Central approval record is unreadable: {path}") from exc
        if not isinstance(approval, dict):
            raise ValueError(f"Central approval record must contain an object: {path}")
        if (
            approval.get("project_id") == project.get("project_id")
            and approval.get("subject_type") == subject_type
            and approval.get("subject_id") == subject_id
            and approval.get("review_status") == "USER_REVIEW_REQUIRED"
            and not approval.get("superseded_by_approval_id")
        ):
            return True
    return False


def _has_existing_subject(root: Path, project: dict, subject_type: str, subject_id: str) -> bool:
    """Any prior decision/request reserves the identity for explicit revision handling."""
    for path in discover_approval_paths(root, project):
        try:
            approval = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Central approval record is unreadable: {path}") from exc
        if not isinstance(approval, dict):
            raise ValueError(f"Central approval record must contain an object: {path}")
        if (
            approval.get("project_id") == project.get("project_id")
            and approval.get("subject_type") == subject_type
            and approval.get("subject_id") == subject_id
        ):
            return True
    return False


def _approval_schema_ref(root: Path, project: dict, approval_path: Path) -> str:
    schema_root = project_path(root, project, "schemas", "00_schemas")
    return Path(os.path.relpath(schema_root / "approval.schema.json", approval_path.parent)).as_posix()


def prepare_review(project_root: str | Path, subject_type: str, subject_id: str, *, requested_by: str, expected_project_sha256: str, expected_subject_sha256: str, supporting_evidence: tuple[str, ...] = (), apply: bool = False) -> dict:
    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    try:
        project = read_project(root)
        project_path = root / "project.json"
        authority, record = _authority(root, project, subject_type, subject_id)
        if not requested_by:
            raise ValueError("requested_by is required")
        if sha256_file(project_path) != expected_project_sha256 or sha256_file(authority) != expected_subject_sha256:
            return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Project or subject changed since caller evaluation")])
        if subject_type not in SUBJECT_GATES:
            raise ValueError("Unsupported subject_type")
        evidence_sources = _supporting_evidence(root, project, subject_type, record, supporting_evidence)
        if _has_existing_subject(root, project, subject_type, subject_id):
            return _result(allowed=False, errors=[issue("E_REVISION_WORKFLOW_UNSUPPORTED", "Existing current approval requires the explicit revision workflow")])
        approval_id, approval_path = _next_approval_id(root, project, SUBJECT_GATES[subject_type])
        if approval_path.exists():
            return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Approval target already exists")])
        version, archive_copies = (None, [])
        if subject_type in FIXED_SUBJECTS:
            version, archive_copies = _archive_plan(root, subject_type, subject_id, authority, evidence_sources)
            if any(destination.exists() for _, destination, _ in archive_copies):
                return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Immutable archive destination already exists")])
        evidence = [{"path": canonical_relpath(authority, root), "sha256": sha256_file(authority), "verified_claim": "Current content authority"}]
        for source, claim in evidence_sources:
            evidence.append({"path": canonical_relpath(source, root), "sha256": sha256_file(source), "verified_claim": claim})
        for source, destination, claim in archive_copies:
            evidence.append({"path": canonical_relpath(destination, root), "sha256": sha256_file(source), "verified_claim": f"Immutable archive mirror: {claim}"})
        payload = {
            "$schema": _approval_schema_ref(root, project, approval_path),
            "schema_id": "cinema-studio-pipeline/approval@2.0.0", "schema_version": "2.0.0",
            "project_id": project.get("project_id"), "approval_id": approval_id,
            "subject_type": subject_type, "subject_id": subject_id, "subject_sha256": sha256_file(authority),
            "gate": SUBJECT_GATES[subject_type], "review_status": "USER_REVIEW_REQUIRED",
            "requested_by": requested_by, "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "evidence": evidence, "supersedes_approval_id": None, "superseded_by_approval_id": None,
        }
        _validate_approval_candidate(root, project, payload)
        candidate_report = validate_review_candidate(root, subject_type, subject_id, payload)
        if not candidate_report.get("ok"):
            return _result(
                allowed=False,
                errors=candidate_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Review candidate validation failed")]),
            )
    except Exception as exc:
        return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", str(exc))])
    result = _result(allowed=True, errors=[], approval_id=approval_id, approval_path=canonical_relpath(approval_path, root), archive_version=version)
    if not apply:
        return result
    created_archive_files: list[tuple[Path, str]] = []
    archive_version_root = archive_copies[0][1].parent if archive_copies else None
    approval_published = False
    try:
        # Use the shared lock for the complete CAS-to-publication window.  A
        # failed later gate sync deliberately never rolls this package back.
        from transition_status import _transition_lock
        with _transition_lock(root):
            if sha256_file(root / "project.json") != expected_project_sha256 or sha256_file(authority) != expected_subject_sha256:
                return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Project or subject changed before publication")])
            candidate_report = validate_review_candidate(root, subject_type, subject_id, payload)
            if not candidate_report.get("ok"):
                return _result(
                    allowed=False,
                    errors=candidate_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Review candidate validation failed inside publication lock")]),
                )
            for source, destination, _ in archive_copies:
                _safe_bytes_copy(root, source, destination)
                created_archive_files.append((destination, sha256_file(destination)))
                if sha256_file(destination) != sha256_file(source):
                    raise ValueError("Immutable archive copy changed during publication")
            for item in evidence:
                candidate = safe_project_path(root, item["path"])
                if not candidate.is_file() or sha256_file(candidate) != item["sha256"]:
                    raise ValueError("Approval evidence changed before publication")
            _validate_approval_candidate(root, project, payload)
            candidate_report = validate_review_candidate(root, subject_type, subject_id, payload)
            if not candidate_report.get("ok"):
                return _result(
                    allowed=False,
                    errors=candidate_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Review candidate validation failed before publication")]),
                )
            _atomic_create_json(root, approval_path, payload)
            approval_published = True
            result["review_prepared"] = True
    except Exception as exc:
        return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", str(exc))])
    finally:
        if not approval_published and created_archive_files:
            _cleanup_unpublished_archive(
                root,
                approval_path,
                archive_version_root,
                created_archive_files,
            )
    try:
        from transition_status import apply_transition
        transitioned = apply_transition(root, SUBJECT_GATES[subject_type], "USER_REVIEW_REQUIRED", expected_project_sha256=expected_project_sha256)
        result["gate_activated"] = bool(transitioned.get("applied"))
        result["gate_transition"] = transitioned
    except Exception as exc:  # Package remains a valid explicit review request.
        result["gate_transition"] = {"allowed": False, "applied": False, "errors": [issue("E_STAGE_PREREQ", str(exc))]}
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("subject_type", choices=tuple(SUBJECT_GATES))
    parser.add_argument("subject_id")
    parser.add_argument("--requested-by", required=True)
    parser.add_argument("--expected-project-sha256", required=True)
    parser.add_argument("--expected-subject-sha256", required=True)
    parser.add_argument("--supporting-evidence", action="append", default=[], metavar="PROJECT_RELATIVE_PATH")
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_review(args.project_root, args.subject_type, args.subject_id, requested_by=args.requested_by, expected_project_sha256=args.expected_project_sha256, expected_subject_sha256=args.expected_subject_sha256, supporting_evidence=tuple(args.supporting_evidence), apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("allowed") or (args.apply and not result.get("review_prepared")):
        return 1
    return 2 if args.apply and not result.get("gate_activated") else 0


if __name__ == "__main__":
    sys.exit(main())
