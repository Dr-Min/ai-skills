#!/usr/bin/env python3
"""Verify immutable media hashes and parent lineage without modifying files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _cinema_common import (
    canonical_relpath,
    discover_approval_paths,
    discover_asset_paths,
    discover_take_paths,
    find_bound_approvals,
    issue,
    read_json,
    read_project,
    safe_project_path,
    sha256_file,
)


ROOT_DERIVATIONS = {"GENERATION", "IMPORTED", "RECORDED"}


def _resolve_media_path(raw_path: str, project_root: Path, record_path: Path) -> Path:
    del record_path  # v2 media paths are always project-relative, never record-relative.
    return safe_project_path(project_root, raw_path)


def _asset_records(project_root: Path, project: dict, approvals: list[tuple[dict, Path]], errors: list[dict]) -> list[dict]:
    result: list[dict] = []
    for record_path in discover_asset_paths(project_root, project):
        try:
            asset = read_json(record_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(record_path, project_root)))
            continue
        if not isinstance(asset, dict) or not isinstance(asset.get("asset_id"), str):
            continue
        lineage = asset.get("lineage") if isinstance(asset.get("lineage"), dict) else {}
        file_slots: list[tuple[str, str | None, str | None]] = []
        files = asset.get("files")
        if isinstance(files, dict):
            for slot_name, slot in files.items():
                if isinstance(slot, dict):
                    file_slots.append((slot_name, slot.get("path"), slot.get("sha256")))
        # Read-only compatibility for projects created before the v2 schema.
        if not file_slots:
            raw_path = next((asset.get(key) for key in ("file", "output_file", "path") if isinstance(asset.get(key), str)), None)
            if raw_path:
                file_slots.append(("legacy_output", raw_path, lineage.get("output_sha256")))
        primary = next((slot for slot in file_slots if slot[0] == "immutable_master"), file_slots[0] if file_slots else (None, None, None))
        try:
            target_path = safe_project_path(project_root, primary[1]) if isinstance(primary[1], str) else None
        except ValueError:
            target_path = None
        decisions = (
            find_bound_approvals(
                project_root,
                approvals,
                project_id=str(project.get("project_id", "")),
                subject_type="ASSET",
                subject_id=asset["asset_id"],
                gate="ASSET_LOCK",
                target_path=target_path,
                statuses={"USER_REVIEW_REQUIRED", "USER_APPROVED"},
                require_current=True,
            )
            if target_path is not None
            else []
        )
        decision = decisions[0][0] if len(decisions) == 1 else None
        result.append(
            {
                "id": asset["asset_id"],
                "record_type": "ASSET",
                "record": asset,
                "record_path": record_path,
                "file_slots": file_slots,
                "output_path": primary[1],
                "output_sha256": lineage.get("output_sha256") or primary[2],
                "parent_id": lineage.get("parent_asset_id"),
                "immutable_master_id": lineage.get("immutable_master_asset_id"),
                "derivation": lineage.get("derivation"),
                "input_hashes": lineage.get("input_hashes", []),
                "source_files": lineage.get("source_files", []),
                "source_ids": [],
                "approved": decision is not None,
                "approval_id": decision.get("approval_id") if decision is not None else None,
                "immutable": asset.get("immutable") is True or primary[0] == "immutable_master",
            }
        )
    return result


def _take_records(project_root: Path, project: dict, approvals: list[tuple[dict, Path]], errors: list[dict]) -> list[dict]:
    result: list[dict] = []
    for path in discover_take_paths(project_root, project):
        try:
            payload = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(path, project_root)))
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("take_id"), str):
            continue
        lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
        try:
            target_path = safe_project_path(project_root, payload.get("output_file")) if isinstance(payload.get("output_file"), str) else None
        except ValueError:
            target_path = None
        decisions = (
            find_bound_approvals(
                project_root,
                approvals,
                project_id=str(project.get("project_id", "")),
                subject_type="TAKE",
                subject_id=payload["take_id"],
                gate="RAW_VIDEO",
                target_path=target_path,
                statuses={"USER_REVIEW_REQUIRED", "USER_APPROVED"},
                require_current=True,
            )
            if target_path is not None
            else []
        )
        decision = decisions[0][0] if len(decisions) == 1 else None
        result.append(
            {
                "id": payload["take_id"],
                "record_type": "TAKE",
                "record": payload,
                "record_path": path,
                "file_slots": [("output", payload.get("output_file"), payload.get("output_sha256"))],
                "output_path": payload.get("output_file"),
                "output_sha256": payload.get("output_sha256"),
                "parent_id": lineage.get("parent_take_id") or payload.get("parent_take_id"),
                "immutable_master_id": None,
                "derivation": lineage.get("derivation"),
                "input_hashes": payload.get("input_hashes", []),
                "source_files": [],
                "source_ids": [
                    value
                    for key in ("source_asset_ids", "source_take_ids")
                    for value in (lineage.get(key, []) if isinstance(lineage.get(key), list) else [])
                    if isinstance(value, str)
                ],
                "approved": decision is not None,
                "approval_id": decision.get("approval_id") if decision is not None else None,
                "immutable": decision is not None,
            }
        )
    return result


def _check_hash(
    raw_path: str | None,
    expected: str | None,
    record: dict,
    project_root: Path,
    errors: list[dict],
    *,
    slot_name: str,
) -> Path | None:
    if not raw_path:
        if record["approved"]:
            errors.append(issue("APPROVAL_HASH_MISSING", f"Approved {record['record_type'].lower()} {record['id']} has no {slot_name} path", path=canonical_relpath(record["record_path"], project_root)))
        return None
    try:
        resolved = _resolve_media_path(raw_path, project_root, record["record_path"])
    except ValueError as exc:
        errors.append(issue("PATH_ESCAPE", str(exc), path=canonical_relpath(record["record_path"], project_root), record_id=record["id"], slot=slot_name))
        return None
    if not resolved.is_file():
        errors.append(issue("LINEAGE_FILE_MISSING", f"Lineage file not found: {raw_path}", path=canonical_relpath(record["record_path"], project_root), record_id=record["id"], slot=slot_name))
        return resolved
    if not expected:
        if record["approved"] or record["immutable"]:
            errors.append(issue("APPROVAL_HASH_MISSING", f"Immutable output has no SHA-256: {record['id']} ({slot_name})", path=canonical_relpath(record["record_path"], project_root)))
        return resolved
    actual = sha256_file(resolved)
    if actual.casefold() != str(expected).casefold():
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"SHA-256 mismatch for {record['id']} ({slot_name})", path=canonical_relpath(resolved, project_root), expected=expected, actual=actual))
    return resolved


def _check_cycles(records_by_id: dict[str, dict], errors: list[dict]) -> None:
    done: set[str] = set()
    for start in records_by_id:
        if start in done:
            continue
        current: str | None = start
        chain: list[str] = []
        positions: dict[str, int] = {}
        while current and current in records_by_id:
            if current in positions:
                cycle = chain[positions[current] :] + [current]
                errors.append(issue("LINEAGE_CYCLE", "Lineage parent cycle detected", record_ids=cycle))
                break
            if current in done:
                break
            positions[current] = len(chain)
            chain.append(current)
            parent = records_by_id[current].get("parent_id")
            current = parent if isinstance(parent, str) else None
        done.update(chain)


def verify_lineage(project_root: str | Path) -> dict:
    """Verify lineage hashes, graph integrity, and immutable parent usage."""

    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    warnings: list[dict] = []
    if not root.is_dir():
        return {"ok": False, "errors": [issue("PROJECT_NOT_FOUND", f"Project directory not found: {root}")], "warnings": [], "records_checked": 0}
    try:
        project = read_project(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "errors": [issue("PROJECT_FILE_MISSING", str(exc))], "warnings": [], "records_checked": 0}
    try:
        approvals: list[tuple[dict, Path]] = []
        for approval_path in discover_approval_paths(root, project):
            try:
                approval = read_json(approval_path)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(issue("INVALID_JSON", str(exc), path=canonical_relpath(approval_path, root)))
                continue
            if isinstance(approval, dict):
                approvals.append((approval, approval_path))
        records = _asset_records(root, project, approvals, errors) + _take_records(root, project, approvals, errors)
    except ValueError as exc:
        return {
            "ok": False,
            "errors": errors + [issue("PATH_ESCAPE", str(exc))],
            "warnings": warnings,
            "records_checked": 0,
        }
    records_by_id: dict[str, dict] = {}
    for record in records:
        if record["id"] in records_by_id:
            errors.append(issue("DUPLICATE_ID", f"Duplicate lineage id: {record['id']}"))
        records_by_id[record["id"]] = record

    resolved_outputs: dict[str, Path] = {}
    for record in records:
        if record["approved"] and not record.get("approval_id"):
            errors.append(issue("APPROVAL_HASH_MISSING", f"Approved {record['record_type'].lower()} {record['id']} has no approval_id", path=canonical_relpath(record["record_path"], root)))
        for slot_name, raw_path, slot_hash in record["file_slots"]:
            expected = slot_hash
            if slot_name in {"immutable_master", "output", "legacy_output"}:
                output_hash = record.get("output_sha256")
                if expected and output_hash and str(expected).casefold() != str(output_hash).casefold():
                    errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Recorded output hashes disagree for {record['id']}", path=canonical_relpath(record["record_path"], root), slot_hash=expected, lineage_hash=output_hash))
                expected = output_hash or expected
            resolved = _check_hash(raw_path, expected, record, root, errors, slot_name=slot_name)
            if resolved is not None and slot_name in {"immutable_master", "output", "legacy_output"}:
                resolved_outputs[record["id"]] = resolved
        input_hashes = record.get("input_hashes")
        if isinstance(input_hashes, list):
            for input_hash in input_hashes:
                if not isinstance(input_hash, dict):
                    continue
                _check_hash(input_hash.get("path"), input_hash.get("sha256"), {**record, "approved": True, "immutable": True}, root, errors, slot_name="input")

    for record in records:
        parent_id = record.get("parent_id")
        if parent_id:
            parent = records_by_id.get(parent_id)
            if parent is None:
                errors.append(issue("LINEAGE_PARENT_MISSING", f"Unknown parent {parent_id} for {record['id']}"))
            else:
                child_output = resolved_outputs.get(record["id"])
                parent_output = resolved_outputs.get(parent_id)
                if child_output is not None and parent_output is not None and child_output == parent_output:
                    errors.append(issue("LINEAGE_OVERWRITE", f"Derivative {record['id']} reuses parent output path", path=canonical_relpath(child_output, root), parent_id=parent_id))
                if record.get("derivation") == "PATCH_FROM_MASTER" and parent.get("derivation") not in ROOT_DERIVATIONS:
                    errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"PATCH_FROM_MASTER {record['id']} uses derivative parent {parent_id}"))
        master_id = record.get("immutable_master_id")
        if master_id:
            master = records_by_id.get(master_id)
            if master is None:
                errors.append(issue("LINEAGE_MASTER_MISSING", f"Unknown immutable master {master_id} for {record['id']}"))
            elif master.get("parent_id") or master.get("derivation") not in ROOT_DERIVATIONS:
                errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Immutable master pointer for {record['id']} targets derivative {master_id}"))
            elif record.get("derivation") in {"PATCH_FROM_MASTER", "CROP_FROM_MASTER"}:
                master_output = resolved_outputs.get(master_id)
                master_hash = master.get("output_sha256")
                bound_paths: list[Path] = []
                for raw_path in record.get("source_files", []) if isinstance(record.get("source_files"), list) else []:
                    try:
                        bound_paths.append(_resolve_media_path(raw_path, root, record["record_path"]))
                    except ValueError:
                        continue
                for item in record.get("input_hashes", []) if isinstance(record.get("input_hashes"), list) else []:
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        continue
                    try:
                        input_path = _resolve_media_path(item["path"], root, record["record_path"])
                    except ValueError:
                        continue
                    bound_paths.append(input_path)
                    if master_hash and str(item.get("sha256", "")).casefold() != str(master_hash).casefold():
                        errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Patch input hash is not the declared immutable master: {record['id']}", parent_id=master_id))
                if master_output is None or not bound_paths or any(path != master_output for path in bound_paths):
                    errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Patch inputs are not bound to declared immutable master {master_id}: {record['id']}"))
        for source_id in record.get("source_ids", []):
            if source_id not in records_by_id:
                errors.append(issue("LINEAGE_SOURCE_MISSING", f"Unknown source {source_id} for {record['id']}"))

        # An identifier link is not sufficient provenance. Every declared
        # parent/master/source must be bound by an input record to the exact
        # current authoritative output path and SHA-256 of that source.
        declared_sources = {
            source_id
            for source_id in (
                [record.get("parent_id"), record.get("immutable_master_id")]
                + list(record.get("source_ids", []))
            )
            if isinstance(source_id, str)
        }
        input_bindings: set[tuple[Path, str]] = set()
        for item in record.get("input_hashes", []) if isinstance(record.get("input_hashes"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                continue
            try:
                input_bindings.add(
                    (
                        _resolve_media_path(item["path"], root, record["record_path"]),
                        item["sha256"].casefold(),
                    )
                )
            except ValueError:
                continue
        for source_id in declared_sources:
            source = records_by_id.get(source_id)
            if source is None:
                continue
            source_path = resolved_outputs.get(source_id)
            source_hash = source.get("output_sha256")
            if (
                source_path is None
                or not isinstance(source_hash, str)
                or (source_path, source_hash.casefold()) not in input_bindings
            ):
                errors.append(
                    issue(
                        "E_DERIVATIVE_AS_EDIT_BASE",
                        f"{record['record_type'].title()} input does not bind authoritative source {source_id}: {record['id']}",
                        path=canonical_relpath(record["record_path"], root),
                        source_id=source_id,
                    )
                )
    _check_cycles(records_by_id, errors)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "records_checked": len(records)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_lineage(args.project_root)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["ok"] else "FAIL")
        for item in result["errors"]:
            print(f"ERROR {item['code']}: {item['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
