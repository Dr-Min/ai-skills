#!/usr/bin/env python3
"""Fail-closed evaluation and guarded application of Cinema Studio stage changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from _cinema_common import (
    authority_path,
    discover_approval_paths,
    discover_asset_paths,
    discover_shot_paths,
    discover_take_paths,
    find_bound_approvals,
    issue,
    is_name_redirecting_reparse,
    offline_remote_package_error,
    read_json,
    read_project,
    safe_project_path,
    sha256_file,
    write_json,
)
from decision_receipts import verify_decision_receipt


ERROR_CODES = frozenset(
    {
        "E_STAGE_PREREQ",
        "E_UNAPPROVED_INPUT",
        "E_EXCLUDED_INPUT",
        "E_MUTEX_REFERENCE",
        "E_REFERENCE_ROLE_CONFLICT",
        "E_APPROVAL_HASH_MISMATCH",
        "E_DERIVATIVE_AS_EDIT_BASE",
        "E_REMOTE_PROOF_MISSING",
        "E_SOURCE_LIBRARY_UNLOCKED",
    }
)
STAGES = (
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
COLLECTION_GATES = frozenset({"ASSET_LOCK", "SHOT_STILL", "RAW_VIDEO"})
TERMINAL_COLLECTION_STATUSES = frozenset(
    {"USER_APPROVED", "REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
)
REVIEW_REQUEST_STATUS = frozenset({"USER_REVIEW_REQUIRED"})
OFFLINE_VERIFICATION = {
    "verification_scope": "OFFLINE_RECORD_CONSISTENCY",
    "remote_truth_verified": False,
}
ALLOWED_TRANSITIONS = {
    # A complete, exact-hash central review package is the guard for the
    # direct path. evaluate_transition() still rejects an unprepared draft.
    "DRAFT": {"INTERNAL_REVIEW", "USER_REVIEW_REQUIRED"},
    "INTERNAL_REVIEW": {"DRAFT", "USER_REVIEW_REQUIRED"},
    "USER_REVIEW_REQUIRED": {"USER_APPROVED", "REJECTED"},
    "USER_APPROVED": {"SUPERSEDED"},
    "REJECTED": {"DRAFT", "EXCLUDED_FROM_INPUTS"},
    "LEGACY_UNVERIFIED": {"INTERNAL_REVIEW", "EXCLUDED_FROM_INPUTS"},
    "SUPERSEDED": {"DRAFT"},
    "EXCLUDED_FROM_INPUTS": set(),
}
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


class TransitionLockBusy(RuntimeError):
    pass


def _stage_project_json(project_path: Path, project: dict) -> Path:
    """Serialize and fsync a candidate before the final CAS checks."""

    staged = project_path.with_name(
        f".{project_path.name}.{uuid.uuid4().hex}.stage.json"
    )
    write_json(staged, project)
    return staged


@contextmanager
def _transition_lock(root: Path):
    key = str(root.resolve()).casefold()
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(blocking=False):
        raise TransitionLockBusy("Another transition is already evaluating this project")
    resolved_root = root.resolve()
    lock_path = resolved_root / ".cinema-transition.lock"
    handle = None
    locked = False
    try:
        if lock_path.parent.resolve() != resolved_root:
            raise TransitionLockBusy("Transition lock is not a direct child of the project root")
        try:
            existing = os.lstat(lock_path)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise TransitionLockBusy(f"Transition lock cannot be inspected safely: {exc}") from exc
        if existing is not None and (
            is_name_redirecting_reparse(lock_path) or existing.st_nlink > 1
        ):
            raise TransitionLockBusy("Transition lock must not be a symlink, reparse point, or hardlink alias")
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            opened = os.fstat(descriptor)
            linked = os.lstat(lock_path)
            if (
                is_name_redirecting_reparse(lock_path)
                or opened.st_nlink > 1
                or linked.st_nlink > 1
                or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)
            ):
                os.close(descriptor)
                raise TransitionLockBusy("Transition lock path changed or resolved through an alias")
            handle = os.fdopen(descriptor, "r+b")
        except TransitionLockBusy:
            raise
        except OSError as exc:
            raise TransitionLockBusy(f"Transition lock cannot be opened safely: {exc}") from exc
        if opened.st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise TransitionLockBusy("Another process is applying a project transition") from exc
        yield
    finally:
        if handle is not None:
            if locked:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            handle.close()
        thread_lock.release()


def _read_records(root: Path, project: dict) -> list[tuple[dict, Path]]:
    records: list[tuple[dict, Path]] = []
    for path in (
        discover_approval_paths(root, project)
        + discover_asset_paths(root, project)
        + discover_shot_paths(root, project)
        + discover_take_paths(root, project)
    ):
        try:
            payload = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append((payload, path))
    return records


def _approval_candidates(
    records: list[tuple[dict, Path]],
    gate: str,
    project_id: str,
    *,
    statuses: frozenset[str] | set[str] = frozenset({"USER_APPROVED"}),
) -> list[tuple[dict, Path]]:
    return sorted(
        [
        (record, path)
        for record, path in records
        if record.get("approval_id")
        and record.get("gate") == gate
        and record.get("review_status") in statuses
        and record.get("project_id") == project_id
        and record.get("subject_type") == GATE_SUBJECT_TYPES[gate]
        and not record.get("superseded_by_approval_id")
        ],
        key=lambda item: (str(item[0].get("approval_id")), item[1].as_posix().casefold()),
    )


def _approval_for_gate(
    records: list[tuple[dict, Path]], gate: str, project_id: str
) -> tuple[dict, Path] | None:
    candidates = _approval_candidates(records, gate, project_id)
    return candidates[0] if len(candidates) == 1 else None


def _active_approval_for_gate(
    records: list[tuple[dict, Path]],
    gate: str,
    project_id: str,
    active_ids: set[str],
    errors: list[dict],
) -> tuple[dict, Path] | None:
    active_gate_records = [
        item
        for item in records
        if item[0].get("gate") == gate
        and item[0].get("review_status") == "USER_APPROVED"
        and item[0].get("approval_id") in active_ids
    ]
    eligible = [
        item
        for item in active_gate_records
        if item[0].get("project_id") == project_id
        and item[0].get("subject_type") == GATE_SUBJECT_TYPES[gate]
        and not item[0].get("superseded_by_approval_id")
    ]
    if len(active_gate_records) != 1 or len(eligible) != 1:
        errors.append(
            issue(
                "E_STAGE_PREREQ",
                f"{gate} requires exactly one active concrete same-project USER_APPROVED approval",
            )
        )
        return None
    return eligible[0]


def _collection_records(
    records: list[tuple[dict, Path]], gate: str
) -> list[tuple[dict, Path]]:
    if gate == "ASSET_LOCK":
        return [(record, path) for record, path in records if isinstance(record.get("asset_id"), str)]
    if gate == "SHOT_STILL":
        return [
            (record, path)
            for record, path in records
            if isinstance(record.get("shot_id"), str) and not record.get("take_id")
        ]
    return [(record, path) for record, path in records if isinstance(record.get("take_id"), str)]


def _collection_record_id(record: dict, gate: str) -> str | None:
    key = {"ASSET_LOCK": "asset_id", "SHOT_STILL": "shot_id", "RAW_VIDEO": "take_id"}[gate]
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def _collection_authority_path(
    root: Path, record: dict, record_path: Path, gate: str
) -> Path | None:
    if gate == "SHOT_STILL":
        return record_path.resolve()
    if gate == "ASSET_LOCK":
        files = record.get("files") if isinstance(record.get("files"), dict) else {}
        master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
        raw_path = master.get("path")
    else:
        raw_path = record.get("output_file")
    if not isinstance(raw_path, str):
        return None
    try:
        return safe_project_path(root, raw_path)
    except ValueError:
        return None


def _validate_collection_gate(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    gate: str,
    active_ids: set[str],
    errors: list[dict],
    *,
    require_active: bool,
) -> list[tuple[dict, Path]]:
    project_id = project.get("project_id")
    production_records = _collection_records(records, gate)
    if not production_records:
        errors.append(issue("E_STAGE_PREREQ", f"{gate} requires at least one current production record"))
        return []
    # Production records are self-hashed content authorities. Lifecycle state
    # lives only in central approval records, so derive a temporary operational
    # view instead of reading removed top-level status/approval fields.
    approvals = [
        item
        for item in records
        if item[0].get("subject_type") == GATE_SUBJECT_TYPES[gate]
        and item[0].get("gate") == gate
    ]
    normalized: list[tuple[dict, Path]] = []
    for record, record_path in production_records:
        record_id = _collection_record_id(record, gate)
        target_path = _collection_authority_path(root, record, record_path, gate)
        matches = (
            find_bound_approvals(
                root,
                approvals,
                project_id=str(project.get("project_id", "")),
                subject_type=GATE_SUBJECT_TYPES[gate],
                subject_id=record_id or "",
                gate=gate,
                target_path=target_path,
                statuses=TERMINAL_COLLECTION_STATUSES,
                require_current=True,
            )
            if record_id and target_path is not None
            else []
        )
        derived = dict(record)
        if len(matches) == 1:
            derived["review_status"] = matches[0][0].get("review_status")
            derived["approval_id"] = matches[0][0].get("approval_id")
        normalized.append((derived, record_path))
    production_records = normalized
    selected: list[tuple[dict, Path]] = []
    for record, record_path in production_records:
        record_id = _collection_record_id(record, gate) or "<unknown>"
        status_value = record.get("review_status")
        if status_value not in TERMINAL_COLLECTION_STATUSES:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    f"{gate} record {record_id} is not in a terminal review status",
                    path=str(record_path),
                )
            )
            continue
        if status_value != "USER_APPROVED":
            continue
        approval_id = record.get("approval_id")
        if record.get("project_id") != project_id or not isinstance(approval_id, str):
            errors.append(
                issue(
                    "E_UNAPPROVED_INPUT",
                    f"{gate} record {record_id} lacks same-project approval binding",
                    path=str(record_path),
                )
            )
            continue
        matches = [
            (approval, approval_path)
            for approval, approval_path in records
            if approval.get("approval_id") == approval_id
            and approval.get("gate") == gate
            and approval.get("project_id") == project_id
            and approval.get("subject_type") == GATE_SUBJECT_TYPES[gate]
            and approval.get("subject_id") == record_id
            and approval.get("review_status") == "USER_APPROVED"
            and not approval.get("superseded_by_approval_id")
        ]
        if len(matches) != 1:
            errors.append(
                issue(
                    "E_UNAPPROVED_INPUT",
                    f"{gate} record {record_id} does not resolve to exactly one current central approval",
                    path=str(record_path),
                )
            )
            continue
        approval_item = matches[0]
        if require_active and approval_id not in active_ids:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    f"{gate} record {record_id} approval is not active",
                    path=str(record_path),
                )
            )
        _check_approval(root, approval_item, gate, errors)
        try:
            _check_gate_authority(root, project, records, approval_item, gate, errors)
        except ValueError as exc:
            errors.append(issue("E_STAGE_PREREQ", f"Unsafe {gate} authority for {record_id}: {exc}"))
        selected.append(approval_item)

    storyboard: dict | None = None
    try:
        storyboard_path = authority_path(root, project, "storyboard", "02_storyboard/storyboard.json")
        if storyboard_path.is_file():
            payload = read_json(storyboard_path)
            storyboard = payload if isinstance(payload, dict) else None
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(issue("E_STAGE_PREREQ", f"Cannot read the project-wide storyboard plan: {exc}"))

    if isinstance(storyboard, dict) and gate in {"ASSET_LOCK", "SHOT_STILL"}:
        plan_key = "asset_plan" if gate == "ASSET_LOCK" else "shot_plan"
        id_key = "asset_id" if gate == "ASSET_LOCK" else "shot_id"
        noun = "asset" if gate == "ASSET_LOCK" else "shot"
        raw_plan = storyboard.get(plan_key)
        if isinstance(raw_plan, list):
            planned_ids = {
                item.get(id_key)
                for item in raw_plan
                if isinstance(item, dict) and isinstance(item.get(id_key), str)
            }
            approved_ids = {
                _collection_record_id(record, gate)
                for record, _ in production_records
                if record.get("review_status") == "USER_APPROVED"
            }
            for missing_id in sorted(planned_ids - approved_ids):
                errors.append(issue("E_STAGE_PREREQ", f"{gate} is missing USER_APPROVED planned {noun}: {missing_id}"))
            excluded_statuses = {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
            for record, record_path in production_records:
                record_id = _collection_record_id(record, gate)
                if record_id in planned_ids or record.get("review_status") in excluded_statuses:
                    continue
                errors.append(issue("E_STAGE_PREREQ", f"Unplanned production {noun} must be explicitly rejected, superseded, or excluded: {record_id}", path=str(record_path)))
            if gate == "ASSET_LOCK":
                plan_by_id = {
                    item.get("asset_id"): item
                    for item in raw_plan
                    if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
                }
                for record, record_path in production_records:
                    if record.get("review_status") != "USER_APPROVED":
                        continue
                    asset_id = record.get("asset_id")
                    planned = plan_by_id.get(asset_id)
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
                                f"USER_APPROVED asset {asset_id} kind/state does not match storyboard asset_plan",
                                path=str(record_path),
                            )
                        )

    if isinstance(storyboard, dict) and gate == "RAW_VIDEO" and isinstance(storyboard.get("shot_plan"), list):
        minimums: dict[str, int] = {}
        for planned_shot in storyboard["shot_plan"]:
            if not isinstance(planned_shot, dict):
                continue
            for requirement in planned_shot.get("coverage_requirements", []) if isinstance(planned_shot.get("coverage_requirements"), list) else []:
                if not isinstance(requirement, dict):
                    continue
                coverage_id, minimum = requirement.get("coverage_id"), requirement.get("minimum_approved_takes")
                if isinstance(coverage_id, str) and isinstance(minimum, int) and minimum >= 1:
                    minimums[coverage_id] = minimum
        counts = {coverage_id: 0 for coverage_id in minimums}
        for record, _ in production_records:
            if record.get("review_status") != "USER_APPROVED":
                continue
            for coverage_id in record.get("coverage_requirement_ids", []) if isinstance(record.get("coverage_requirement_ids"), list) else []:
                if coverage_id in counts:
                    counts[coverage_id] += 1
        for coverage_id, minimum in minimums.items():
            if counts[coverage_id] < minimum:
                errors.append(issue("E_STAGE_PREREQ", f"RAW_VIDEO coverage {coverage_id} requires {minimum} USER_APPROVED takes; found {counts[coverage_id]}"))
    if not selected:
        errors.append(issue("E_UNAPPROVED_INPUT", f"{gate} requires at least one USER_APPROVED production record"))
    if require_active:
        expected_ids = {item[0].get("approval_id") for item in selected}
        active_gate_ids = {
            record.get("approval_id")
            for record, _ in records
            if record.get("gate") == gate and record.get("approval_id") in active_ids
        }
        if active_gate_ids != expected_ids:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    f"{gate} active approval set does not exactly cover its current USER_APPROVED records",
                    expected=sorted(str(item) for item in expected_ids),
                    actual=sorted(str(item) for item in active_gate_ids),
                )
            )
    return selected


def _validate_collection_review_ready(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    gate: str,
    errors: list[dict],
) -> list[tuple[dict, Path]]:
    """Require a complete central review package set before caching collection review state."""

    production_records = _collection_records(records, gate)
    if not production_records:
        errors.append(issue("E_STAGE_PREREQ", f"{gate} requires at least one current production record"))
        return []
    project_id = str(project.get("project_id", ""))
    approval_records = [
        item
        for item in records
        if item[0].get("subject_type") == GATE_SUBJECT_TYPES[gate]
        and item[0].get("gate") == gate
    ]
    accepted = frozenset(
        {"USER_REVIEW_REQUIRED", "USER_APPROVED", "REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
    )
    review_complete = frozenset({"USER_REVIEW_REQUIRED", "USER_APPROVED"})
    decisions: dict[str, tuple[dict, Path]] = {}
    selected: list[tuple[dict, Path]] = []
    record_by_id: dict[str, dict] = {}
    for record, record_path in production_records:
        record_id = _collection_record_id(record, gate)
        if not record_id:
            errors.append(issue("E_STAGE_PREREQ", f"{gate} contains a record without an identifier", path=str(record_path)))
            continue
        record_by_id[record_id] = record
        target_path = _collection_authority_path(root, record, record_path, gate)
        matches = (
            find_bound_approvals(
                root,
                approval_records,
                project_id=project_id,
                subject_type=GATE_SUBJECT_TYPES[gate],
                subject_id=record_id,
                gate=gate,
                target_path=target_path,
                statuses=accepted,
                require_current=True,
            )
            if target_path is not None
            else []
        )
        if len(matches) != 1:
            errors.append(
                issue(
                    "E_UNAPPROVED_INPUT",
                    f"{gate} record {record_id} requires exactly one current central review package",
                    path=str(record_path),
                )
            )
            continue
        decision = matches[0]
        decisions[record_id] = decision
        if decision[0].get("review_status") in review_complete:
            selected.append(decision)
            if decision[0].get("review_status") == "USER_APPROVED":
                _check_approval(root, decision, gate, errors)
            try:
                _check_gate_authority(root, project, records, decision, gate, errors)
            except ValueError as exc:
                errors.append(issue("E_STAGE_PREREQ", f"Unsafe {gate} authority for {record_id}: {exc}"))

    storyboard: dict | None = None
    try:
        storyboard_path = authority_path(root, project, "storyboard", "02_storyboard/storyboard.json")
        if storyboard_path.is_file():
            payload = read_json(storyboard_path)
            storyboard = payload if isinstance(payload, dict) else None
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(issue("E_STAGE_PREREQ", f"Cannot read the project-wide storyboard plan: {exc}"))

    if gate in {"ASSET_LOCK", "SHOT_STILL"}:
        plan_key = "asset_plan" if gate == "ASSET_LOCK" else "shot_plan"
        id_key = "asset_id" if gate == "ASSET_LOCK" else "shot_id"
        plan = storyboard.get(plan_key) if isinstance(storyboard, dict) else None
        if not isinstance(plan, list):
            errors.append(issue("E_STAGE_PREREQ", f"{gate} requires a readable storyboard {plan_key}"))
        else:
            planned_ids = {
                item.get(id_key)
                for item in plan
                if isinstance(item, dict) and isinstance(item.get(id_key), str)
            }
            ready_ids = {
                record_id
                for record_id, (approval, _) in decisions.items()
                if approval.get("review_status") in review_complete
            }
            for missing in sorted(planned_ids - ready_ids):
                errors.append(issue("E_STAGE_PREREQ", f"{gate} planned subject is not review-complete: {missing}"))
            terminal_extra = {"REJECTED", "SUPERSEDED", "EXCLUDED_FROM_INPUTS"}
            for record_id in sorted(set(record_by_id) - planned_ids):
                decision = decisions.get(record_id)
                if decision is None or decision[0].get("review_status") not in terminal_extra:
                    errors.append(issue("E_STAGE_PREREQ", f"{gate} unplanned subject is not terminal: {record_id}"))
    elif gate == "RAW_VIDEO":
        minimums: dict[str, int] = {}
        for planned_shot in storyboard.get("shot_plan", []) if isinstance(storyboard, dict) else []:
            if not isinstance(planned_shot, dict):
                continue
            for requirement in planned_shot.get("coverage_requirements", []) if isinstance(planned_shot.get("coverage_requirements"), list) else []:
                if isinstance(requirement, dict) and isinstance(requirement.get("coverage_id"), str):
                    minimum = requirement.get("minimum_approved_takes")
                    if isinstance(minimum, int) and minimum >= 1:
                        minimums[requirement["coverage_id"]] = minimum
        counts = {coverage_id: 0 for coverage_id in minimums}
        for record_id, decision in decisions.items():
            if decision[0].get("review_status") not in review_complete:
                continue
            for coverage_id in record_by_id[record_id].get("coverage_requirement_ids", []):
                if coverage_id in counts:
                    counts[coverage_id] += 1
        for coverage_id, minimum in minimums.items():
            if counts[coverage_id] < minimum:
                errors.append(issue("E_STAGE_PREREQ", f"RAW_VIDEO review packages do not cover {coverage_id}: {counts[coverage_id]}/{minimum}"))
    if not selected:
        errors.append(issue("E_UNAPPROVED_INPUT", f"{gate} has no centrally review-complete production record"))
    return selected


def _check_approval(root: Path, approval_item: tuple[dict, Path] | None, gate: str, errors: list[dict]) -> None:
    if approval_item is None:
        errors.append(
            issue(
                "E_UNAPPROVED_INPUT",
                f"No exact terminal central decision exists for {gate}",
            )
        )
        return
    approval, approval_path = approval_item
    receipt_error = verify_decision_receipt(
        root, str(approval.get("project_id", "")), approval, approval_path
    )
    if receipt_error is not None:
        errors.append(
            issue(
                "DECISION_RECEIPT_INVALID",
                f"{gate} decision receipt is invalid: {receipt_error}",
                path=str(approval_path),
            )
        )
    if approval.get("decided_by_type") != "USER" or not approval.get("decided_by"):
        errors.append(
            issue(
                "E_UNAPPROVED_INPUT",
                f"{gate} decision lacks an explicit user actor",
                path=str(approval_path),
            )
        )
    if (
        approval.get("review_status") == "USER_APPROVED"
        and not approval.get("user_evidence_reference")
    ):
        errors.append(
            issue(
                "E_UNAPPROVED_INPUT",
                f"{gate} approval lacks explicit user evidence",
                path=str(approval_path),
            )
        )
    if approval.get("review_status") == "REJECTED" and not approval.get(
        "decision_notes"
    ):
        errors.append(
            issue(
                "E_UNAPPROVED_INPUT",
                f"{gate} rejection lacks explicit decision notes",
                path=str(approval_path),
            )
        )
    subject_hash = approval.get("subject_sha256")
    evidence = approval.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"{gate} approval has no hashed evidence", path=str(approval_path)))
        return
    matched_subject = False
    for item in evidence:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"{gate} approval contains unhashed evidence", path=str(approval_path)))
            continue
        try:
            evidence_path = safe_project_path(root, item["path"])
        except ValueError:
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Approval evidence escapes project root", path=str(item.get("path"))))
            continue
        actual_hash = sha256_file(evidence_path) if evidence_path.is_file() else None
        if actual_hash is None or actual_hash.casefold() != str(item["sha256"]).casefold():
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Approval evidence hash mismatch: {item['path']}", path=str(evidence_path)))
        elif item.get("sha256") == subject_hash:
            matched_subject = True
    if not matched_subject:
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"{gate} approval evidence does not bind the current subject hash", path=str(approval_path)))


def _check_finish_delivery(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    approval: dict,
    approval_path: Path,
    delivery_path: Path,
    errors: list[dict],
) -> None:
    try:
        delivery = read_json(delivery_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(issue("E_STAGE_PREREQ", f"FINISH delivery record is unreadable: {exc}", path=str(delivery_path)))
        return
    if not isinstance(delivery, dict):
        errors.append(issue("E_STAGE_PREREQ", "FINISH delivery authority must be a JSON object", path=str(delivery_path)))
        return
    project_id = project.get("project_id")
    if delivery.get("project_id") != project_id:
        errors.append(issue("E_UNAPPROVED_INPUT", "FINISH delivery belongs to another project", path=str(delivery_path)))
    if delivery.get("delivery_id") != approval.get("subject_id"):
        errors.append(issue("E_UNAPPROVED_INPUT", "FINISH delivery is not bound to the selected DELIVERY approval", path=str(delivery_path)))

    delivery_id = delivery.get("delivery_id")
    version = delivery.get("version")
    if isinstance(delivery_id, str) and isinstance(version, int):
        try:
            actual_relative = delivery_path.resolve().relative_to(root.resolve())
        except ValueError:
            actual_relative = None
        if version == 1:
            expected_relative = Path("08_delivery") / "delivery.json"
            if delivery.get("supersedes_delivery") is not None:
                errors.append(
                    issue(
                        "E_STAGE_PREREQ",
                        "Version 1 delivery must not declare a predecessor",
                        path=str(delivery_path),
                    )
                )
        elif version >= 2:
            expected_relative = (
                Path("08_delivery")
                / "records"
                / delivery_id
                / f"v{version:03d}"
                / "delivery.json"
            )
            predecessor = delivery.get("supersedes_delivery")
            previous_version = version - 1
            previous_relative = (
                Path("08_delivery") / "delivery.json"
                if previous_version == 1
                else Path("08_delivery")
                / "records"
                / delivery_id
                / f"v{previous_version:03d}"
                / "delivery.json"
            )
            predecessor_valid = isinstance(predecessor, dict)
            predecessor_path: Path | None = None
            if predecessor_valid:
                try:
                    predecessor_path = safe_project_path(root, predecessor.get("path"))
                except (TypeError, ValueError):
                    predecessor_path = None
                predecessor_valid = (
                    predecessor.get("delivery_id") == delivery_id
                    and predecessor.get("version") == previous_version
                    and predecessor_path == root.resolve() / previous_relative
                    and predecessor_path.is_file()
                    and sha256_file(predecessor_path) == predecessor.get("sha256")
                )
            predecessor_record = None
            if predecessor_valid and predecessor_path is not None:
                try:
                    predecessor_record = read_json(predecessor_path)
                except (OSError, UnicodeError, json.JSONDecodeError):
                    predecessor_record = None
                predecessor_valid = (
                    isinstance(predecessor_record, dict)
                    and predecessor_record.get("project_id") == project_id
                    and predecessor_record.get("delivery_id") == delivery_id
                    and predecessor_record.get("version") == previous_version
                )
            predecessor_approvals = [
                record
                for record, _ in records
                if isinstance(predecessor, dict)
                and record.get("approval_id") == predecessor.get("approval_id")
                and record.get("gate") == "FINISH"
                and record.get("subject_type") == "DELIVERY"
                and record.get("subject_id") == delivery_id
                and record.get("subject_sha256") == predecessor.get("sha256")
                and record.get("project_id") == project_id
                and record.get("review_status") in {"USER_APPROVED", "REJECTED"}
            ]
            predecessor_valid = (
                predecessor_valid
                and len(predecessor_approvals) == 1
                and approval.get("supersedes_approval_id") == predecessor.get("approval_id")
                and predecessor_approvals[0].get("superseded_by_approval_id")
                == approval.get("approval_id")
            )
            if not predecessor_valid:
                errors.append(
                    issue(
                        "E_APPROVAL_HASH_MISMATCH",
                        "Delivery predecessor contract does not bind the immediate preserved terminal review version",
                        path=str(delivery_path),
                    )
                )
        else:
            expected_relative = None
            errors.append(issue("E_STAGE_PREREQ", "Delivery version must be a positive integer", path=str(delivery_path)))
        if actual_relative != expected_relative:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    "Delivery authority path does not match its version contract",
                    path=str(delivery_path),
                )
            )
    else:
        errors.append(issue("E_STAGE_PREREQ", "Delivery identity/version is invalid", path=str(delivery_path)))

    timeline_path = authority_path(root, project, "timeline", "07_edit/timeline.json")
    source_timeline = delivery.get("source_timeline") if isinstance(delivery.get("source_timeline"), dict) else {}
    try:
        declared_timeline_path = safe_project_path(root, source_timeline.get("path"))
    except (TypeError, ValueError):
        declared_timeline_path = None
    timeline_hash = sha256_file(timeline_path) if timeline_path.is_file() else None
    if (
        declared_timeline_path != timeline_path
        or timeline_hash is None
        or source_timeline.get("sha256") != timeline_hash
    ):
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", "FINISH delivery does not bind the current timeline bytes", path=str(timeline_path)))
        timeline = None
    else:
        try:
            timeline = read_json(timeline_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            timeline = None
    if not isinstance(timeline, dict):
        errors.append(issue("E_STAGE_PREREQ", "FINISH requires a readable current timeline", path=str(timeline_path)))
    else:
        if (
            timeline.get("project_id") != project_id
            or timeline.get("timeline_id") != source_timeline.get("timeline_id")
            or timeline.get("lock_status") != "PICTURE_LOCKED"
        ):
            errors.append(issue("E_STAGE_PREREQ", "FINISH requires the current PICTURE_LOCKED timeline candidate", path=str(timeline_path)))
        active_ids = set(project.get("active_approval_ids", [])) if isinstance(project.get("active_approval_ids"), list) else set()
        edit_approvals = find_bound_approvals(
            root,
            records,
            project_id=str(project_id),
            subject_type="TIMELINE",
            subject_id=str(timeline.get("timeline_id", "")),
            gate="EDIT",
            target_path=timeline_path,
            statuses={"USER_APPROVED"},
            require_current=True,
        )
        if len(edit_approvals) != 1 or edit_approvals[0][0].get("approval_id") not in active_ids:
            errors.append(issue("E_STAGE_PREREQ", "FINISH timeline lacks one active same-project EDIT approval", path=str(timeline_path)))

    derivation = delivery.get("derivation") if isinstance(delivery.get("derivation"), dict) else {}
    input_hashes = derivation.get("input_hashes") if isinstance(derivation.get("input_hashes"), list) else []
    if timeline_hash is None or not any(
        isinstance(item, dict)
        and item.get("sha256") == timeline_hash
        and isinstance(item.get("path"), str)
        and _same_safe_path(root, item.get("path"), timeline_path)
        for item in input_hashes
    ):
        errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", "FINISH derivation does not bind the current timeline input", path=str(delivery_path)))

    required_evidence: set[tuple[str, str]] = {
        (delivery_path.resolve().relative_to(root.resolve()).as_posix(), sha256_file(delivery_path))
    }
    export = delivery.get("export") if isinstance(delivery.get("export"), dict) else {}
    export_path: Path | None
    try:
        export_path = safe_project_path(root, export.get("path"))
    except (TypeError, ValueError):
        export_path = None
    if export_path is None or not export_path.is_file() or sha256_file(export_path) != export.get("sha256"):
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", "FINISH export bytes do not match the delivery record", path=str(export_path or delivery_path)))
    else:
        required_evidence.add((export_path.relative_to(root.resolve()).as_posix(), export.get("sha256")))

    qa = delivery.get("qa") if isinstance(delivery.get("qa"), dict) else {}
    if qa.get("overall_verdict") != "PASS":
        errors.append(issue("E_STAGE_PREREQ", "FINISH delivery QA overall verdict must be PASS", path=str(delivery_path)))
    for name in ("media_integrity", "frame_integrity", "audio_sync", "crop_safety", "rights_clearance"):
        check = qa.get(name) if isinstance(qa.get(name), dict) else {}
        status_value = check.get("status")
        evidence = check.get("evidence") if isinstance(check.get("evidence"), list) else []
        if status_value == "NOT_APPLICABLE":
            if not check.get("reason"):
                errors.append(issue("E_STAGE_PREREQ", f"FINISH QA {name} needs a reason when not applicable", path=str(delivery_path)))
            continue
        if status_value != "PASS" or not evidence:
            errors.append(issue("E_STAGE_PREREQ", f"FINISH QA {name} requires PASS with hashed visual evidence", path=str(delivery_path)))
            continue
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"FINISH QA {name} contains incomplete evidence", path=str(delivery_path)))
                continue
            try:
                evidence_path = safe_project_path(root, item["path"])
            except ValueError:
                evidence_path = None
            if evidence_path is None or not evidence_path.is_file() or sha256_file(evidence_path) != item["sha256"]:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"FINISH QA {name} evidence hash mismatch", path=str(evidence_path or delivery_path)))
            else:
                required_evidence.add((evidence_path.relative_to(root.resolve()).as_posix(), item["sha256"]))

    approval_evidence = approval.get("evidence") if isinstance(approval.get("evidence"), list) else []
    approval_pairs = {
        (item.get("path"), item.get("sha256"))
        for item in approval_evidence
        if isinstance(item, dict)
    }
    missing = sorted(required_evidence - approval_pairs)
    if missing:
        errors.append(
            issue(
                "E_APPROVAL_HASH_MISMATCH",
                "FINISH approval evidence omits delivery, export, or QA bytes",
                path=str(approval_path),
                missing=missing,
            )
        )


def _same_safe_path(root: Path, raw_path: str, expected: Path) -> bool:
    try:
        return safe_project_path(root, raw_path) == expected
    except ValueError:
        return False


def _check_edit_timeline_revision(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    approval: dict,
    timeline: dict,
    timeline_path: Path,
    errors: list[dict],
) -> None:
    """Require an immutable predecessor and bidirectional approval replacement for EDIT v2+."""

    version = timeline.get("version")
    timeline_id = timeline.get("timeline_id")
    if not isinstance(version, int) or version < 2 or not isinstance(timeline_id, str):
        return
    predecessor = timeline.get("supersedes_timeline")
    previous_version = version - 1
    expected_path = (
        root.resolve() / "07_edit" / "timeline.json"
        if previous_version == 1
        else root.resolve()
        / "07_edit"
        / "records"
        / timeline_id
        / f"v{previous_version:03d}"
        / "timeline.json"
    )
    predecessor_path: Path | None = None
    if isinstance(predecessor, dict):
        try:
            predecessor_path = safe_project_path(root, predecessor.get("path"))
        except (TypeError, ValueError):
            predecessor_path = None
    try:
        predecessor_record = (
            read_json(predecessor_path)
            if predecessor_path is not None and predecessor_path.is_file()
            else None
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        predecessor_record = None
    predecessor_hash = (
        sha256_file(predecessor_path)
        if predecessor_path is not None and predecessor_path.is_file()
        else None
    )
    predecessor_approvals = [
        record
        for record, record_path in records
        if isinstance(predecessor, dict)
        and record_path.is_file()
        and record.get("project_id") == project.get("project_id")
        and record.get("approval_id") == predecessor.get("approval_id")
        and record.get("gate") == "EDIT"
        and record.get("subject_type") == "TIMELINE"
        and record.get("subject_id") == timeline_id
        and record.get("subject_sha256") == predecessor_hash
        and record.get("review_status") in {"USER_APPROVED", "REJECTED"}
    ]
    valid = (
        isinstance(predecessor, dict)
        and predecessor.get("timeline_id") == timeline_id
        and predecessor.get("version") == previous_version
        and predecessor_path == expected_path
        and isinstance(predecessor_hash, str)
        and predecessor.get("sha256") == predecessor_hash
        and isinstance(predecessor_record, dict)
        and predecessor_record.get("project_id") == project.get("project_id")
        and predecessor_record.get("timeline_id") == timeline_id
        and predecessor_record.get("version") == previous_version
        and predecessor_record.get("lock_status") == "PICTURE_LOCKED"
        and len(predecessor_approvals) == 1
        and approval.get("supersedes_approval_id") == predecessor.get("approval_id")
        and predecessor_approvals[0].get("superseded_by_approval_id")
        == approval.get("approval_id")
    )
    if not valid:
        errors.append(
            issue(
                "E_APPROVAL_HASH_MISMATCH",
                "Timeline predecessor contract does not bind the immediate preserved terminal version and replacement approval",
                path=str(timeline_path),
            )
        )


def _check_gate_authority(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    approval_item: tuple[dict, Path] | None,
    gate: str,
    errors: list[dict],
) -> None:
    if approval_item is None:
        return
    approval, approval_path = approval_item
    expected_type = GATE_SUBJECT_TYPES[gate]
    if approval.get("subject_type") != expected_type:
        errors.append(issue("E_UNAPPROVED_INPUT", f"{gate} requires concrete subject_type {expected_type}, not {approval.get('subject_type')}", path=str(approval_path)))
        return
    subject_id = approval.get("subject_id")
    fixed_subject_ids = {"STORY": "story-contract", "LOOKDEV": "visual-bible"}
    if gate in fixed_subject_ids and subject_id != fixed_subject_ids[gate]:
        errors.append(
            issue(
                "E_UNAPPROVED_INPUT",
                f"{gate} requires fixed subject_id {fixed_subject_ids[gate]}",
                path=str(approval_path),
            )
        )
    actual_hash: str | None = None
    declared_hash: str | None = None
    target_path: Path | None = None
    direct_authorities = {
        "STORY": ("story_contract", "01_story/STORY_CONTRACT.md"),
        "STORYBOARD": ("storyboard", "02_storyboard/storyboard.json"),
        "LOOKDEV": ("visual_bible", "03_lookdev/VISUAL_BIBLE.md"),
        "SOURCE_LIBRARY": ("source_manifest", "06_source_library/source_manifest.json"),
        "EDIT": ("timeline", "07_edit/timeline.json"),
    }
    if gate in direct_authorities:
        key, default = direct_authorities[gate]
        target_path = authority_path(root, project, key, default)
    elif gate == "FINISH":
        target_path = authority_path(root, project, "delivery_record", "08_delivery/delivery.json")
    elif gate == "ASSET_LOCK":
        for record, _ in records:
            if record.get("asset_id") != subject_id:
                continue
            files = record.get("files") if isinstance(record.get("files"), dict) else {}
            master = files.get("immutable_master") if isinstance(files.get("immutable_master"), dict) else {}
            target_path = safe_project_path(root, master.get("path")) if isinstance(master.get("path"), str) else None
            lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
            declared_hash = lineage.get("output_sha256") or master.get("sha256")
            break
    elif gate == "SHOT_STILL":
        for record, record_path in records:
            if record.get("shot_id") == subject_id and not record.get("take_id"):
                target_path = record_path
                break
    elif gate == "RAW_VIDEO":
        for record, _ in records:
            if record.get("take_id") == subject_id:
                target_path = safe_project_path(root, record.get("output_file")) if isinstance(record.get("output_file"), str) else None
                declared_hash = record.get("output_sha256")
                break
    if target_path is not None and target_path.is_file():
        actual_hash = sha256_file(target_path)
    if actual_hash is None:
        errors.append(issue("E_STAGE_PREREQ", f"{gate} authority target is missing for subject {subject_id}", path=str(approval_path)))
    elif approval.get("subject_sha256") != actual_hash:
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"{gate} approval hash does not match current authority target", path=str(target_path), actual=actual_hash))
    json_id_fields = {
        "STORYBOARD": "storyboard_id",
        "SOURCE_LIBRARY": "library_id",
        "EDIT": "timeline_id",
        "FINISH": "delivery_id",
    }
    if gate in json_id_fields and target_path is not None and target_path.is_file():
        try:
            authority_record = read_json(target_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            authority_record = None
        id_field = json_id_fields[gate]
        if (
            not isinstance(authority_record, dict)
            or authority_record.get("project_id") != project.get("project_id")
            or authority_record.get(id_field) != subject_id
        ):
            errors.append(
                issue(
                    "E_UNAPPROVED_INPUT",
                    f"{gate} approval subject_id must equal the current {id_field}",
                    path=str(target_path),
                )
            )
    if actual_hash is not None and target_path is not None:
        exact_binding = False
        evidence = approval.get("evidence") if isinstance(approval.get("evidence"), list) else []
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            try:
                evidence_path = safe_project_path(root, item["path"])
            except ValueError:
                continue
            if evidence_path == target_path and str(item.get("sha256", "")).casefold() == actual_hash.casefold():
                exact_binding = True
                break
        if not exact_binding:
            errors.append(
                issue(
                    "E_APPROVAL_HASH_MISMATCH",
                    f"{gate} approval evidence does not bind the exact current authority path and hash",
                    path=str(target_path),
                )
            )
    if actual_hash is not None and declared_hash is not None and str(declared_hash).casefold() != actual_hash.casefold():
        errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"{gate} record hash does not match current authority target", path=str(target_path), actual=actual_hash, declared=declared_hash))
    if gate == "EDIT" and target_path is not None and target_path.is_file():
        try:
            timeline = read_json(target_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            timeline = None
        if not isinstance(timeline, dict) or timeline.get("lock_status") != "PICTURE_LOCKED":
            errors.append(issue("E_STAGE_PREREQ", "EDIT approval requires a PICTURE_LOCKED timeline candidate", path=str(target_path)))
        elif isinstance(timeline, dict):
            _check_edit_timeline_revision(
                root,
                project,
                records,
                approval,
                timeline,
                target_path,
                errors,
            )
    if gate == "FINISH" and target_path is not None and target_path.is_file():
        _check_finish_delivery(root, project, records, approval, approval_path, target_path, errors)


def _check_video_proof(root: Path, project: dict, records: list[tuple[dict, Path]], errors: list[dict]) -> None:
    takes = [(record, path) for record, path in records if record.get("take_id")]
    approved: list[tuple[dict, Path]] = []
    for take, path in takes:
        target = _collection_authority_path(root, take, path, "RAW_VIDEO")
        matches = (
            find_bound_approvals(
                root,
                records,
                project_id=str(project.get("project_id", "")),
                subject_type="TAKE",
                subject_id=str(take.get("take_id", "")),
                gate="RAW_VIDEO",
                target_path=target,
                statuses={"USER_APPROVED"},
                require_current=True,
            )
            if target is not None
            else []
        )
        if len(matches) == 1:
            approved.append((take, path))
    if not approved:
        errors.append(issue("E_UNAPPROVED_INPUT", "RAW_VIDEO requires at least one USER_APPROVED take"))
        return
    for take, path in approved:
        remote = take.get("remote") if isinstance(take.get("remote"), dict) else {}
        model = take.get("model") if isinstance(take.get("model"), dict) else {}
        diagnosis = take.get("diagnosis") if isinstance(take.get("diagnosis"), dict) else {}
        if (
            not take.get("coverage_requirement_ids")
            or not take.get("input_hashes")
            or model.get("verified") is not True
            or diagnosis.get("verdict") != "PASS"
            or diagnosis.get("first_failure") is not None
            or not diagnosis.get("what_held")
        ):
            errors.append(issue("E_UNAPPROVED_INPUT", f"Take lacks review-ready coverage/input/model/diagnosis evidence: {take.get('take_id')}", path=str(path)))
        origin = take.get("execution_origin", "REMOTE_GENERATION")
        if origin == "REMOTE_GENERATION":
            job_id = remote.get("job_id")
            if remote.get("verified") is not True or not job_id or model.get("verified") is not True:
                errors.append(issue("E_REMOTE_PROOF_MISSING", f"Take lacks a consistent offline remote evidence record: {take.get('take_id')}", path=str(path)))
            if take.get("remote_job_id") and job_id and take.get("remote_job_id") != job_id:
                errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote job identifiers disagree: {take.get('take_id')}", path=str(path)))
            remote_evidence = remote.get("evidence") if isinstance(remote.get("evidence"), list) else []
            if not remote_evidence:
                errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence record has no hashed evidence: {take.get('take_id')}", path=str(path)))
            for evidence in remote_evidence:
                if not isinstance(evidence, dict) or not evidence.get("path") or not evidence.get("sha256"):
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence is incomplete: {take.get('take_id')}", path=str(path)))
                    continue
                try:
                    evidence_path = safe_project_path(root, evidence["path"])
                except ValueError:
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence escapes project root: {take.get('take_id')}", path=str(path)))
                    continue
                if not evidence_path.is_file() or sha256_file(evidence_path) != evidence["sha256"]:
                    errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence hash mismatch: {take.get('take_id')}", path=str(evidence_path)))
                else:
                    package_error = offline_remote_package_error(evidence_path, take, record_type="TAKE")
                    if package_error:
                        errors.append(issue("E_REMOTE_PROOF_MISSING", f"Remote evidence package is inconsistent for {take.get('take_id')}: {package_error}", path=str(evidence_path)))
        elif origin == "LOCAL_PROCESSING":
            if (
                remote.get("verified") is not False
                or remote.get("job_id") is not None
                or take.get("remote_job_id") is not None
                or take.get("remote_url") is not None
                or model.get("verified") is not True
                or not model.get("name")
                or not model.get("version")
                or not take.get("generation_parameters")
            ):
                errors.append(issue("E_UNAPPROVED_INPUT", f"Local-processing provenance is incomplete or claims remote state: {take.get('take_id')}", path=str(path)))
            input_hashes = take.get("input_hashes") if isinstance(take.get("input_hashes"), list) else []
            if not input_hashes:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local processing lacks input hashes: {take.get('take_id')}", path=str(path)))
            for item in input_hashes:
                try:
                    input_path = safe_project_path(root, item.get("path")) if isinstance(item, dict) else None
                except ValueError:
                    input_path = None
                if input_path is None or not input_path.is_file() or sha256_file(input_path) != item.get("sha256"):
                    errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local input hash mismatch: {take.get('take_id')}", path=str(path)))
            try:
                output_path = safe_project_path(root, take.get("output_file"))
            except (TypeError, ValueError):
                output_path = None
            if output_path is None or not output_path.is_file() or sha256_file(output_path) != take.get("output_sha256"):
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Local output hash mismatch: {take.get('take_id')}", path=str(path)))
            lineage = take.get("lineage") if isinstance(take.get("lineage"), dict) else {}
            if not lineage.get("parent_take_id") and not lineage.get("source_take_ids") and not lineage.get("source_asset_ids"):
                errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Local processing lacks lineage sources: {take.get('take_id')}", path=str(path)))
            if diagnosis.get("verdict") != "PASS" or not diagnosis.get("what_held"):
                errors.append(issue("E_UNAPPROVED_INPUT", f"Local processing diagnosis has not passed: {take.get('take_id')}", path=str(path)))
        else:
            errors.append(issue("E_UNAPPROVED_INPUT", f"Unknown execution_origin: {origin}", path=str(path)))


def _check_source_library(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    errors: list[dict],
) -> None:
    manifest_path = authority_path(root, project, "source_manifest", "06_source_library/source_manifest.json")
    if not manifest_path.is_file():
        errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", "Source library manifest is missing"))
        return
    try:
        manifest = read_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", str(exc), path=str(manifest_path)))
        return
    lock_status = manifest.get("lock_status") if isinstance(manifest, dict) else None
    if lock_status != "SOURCE_LOCKED":
        errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", "Source library must be SOURCE_LOCKED before edit"))
    if isinstance(manifest, dict):
        library_approvals = find_bound_approvals(
            root,
            records,
            project_id=str(project.get("project_id", "")),
            subject_type="SOURCE_LIBRARY",
            subject_id=str(manifest.get("library_id", "")),
            gate="SOURCE_LIBRARY",
            target_path=manifest_path,
            statuses={"USER_APPROVED"},
            require_current=True,
        )
        if len(library_approvals) != 1:
            errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", "Source library does not resolve to one exact current central USER_APPROVED decision"))
            errors.append(issue("E_APPROVAL_HASH_MISMATCH", "Source library decision does not bind the current manifest path and hash", path=str(manifest_path)))
        else:
            _check_approval(root, library_approvals[0], "SOURCE_LIBRARY", errors)
        takes = {
            record.get("take_id"): (record, path)
            for record, path in records
            if isinstance(record.get("take_id"), str)
        }
        for source in manifest.get("sources", []) if isinstance(manifest.get("sources"), list) else []:
            if not isinstance(source, dict):
                continue
            if source.get("source_status") == "EXCLUDED":
                errors.append(issue("E_EXCLUDED_INPUT", f"Excluded source remains in the locked library: {source.get('source_id')}"))
            elif source.get("source_status") != "SOURCE_APPROVED":
                errors.append(issue("E_UNAPPROVED_INPUT", f"Source is not SOURCE_APPROVED: {source.get('source_id')}"))
            raw_path = source.get("path")
            expected = source.get("sha256")
            try:
                resolved = safe_project_path(root, raw_path) if isinstance(raw_path, str) else None
            except ValueError:
                resolved = None
            if not expected or resolved is None or not resolved.is_file() or sha256_file(resolved) != expected:
                errors.append(issue("E_APPROVAL_HASH_MISMATCH", f"Source hash mismatch: {source.get('source_id')}"))
            take_item = takes.get(source.get("take_id"))
            take = take_item[0] if take_item is not None else None
            take_path = take_item[1] if take_item is not None else None
            take_approvals = []
            if isinstance(take, dict) and isinstance(take_path, Path) and resolved is not None:
                take_approvals = find_bound_approvals(
                    root,
                    records,
                    project_id=str(project.get("project_id", "")),
                    subject_type="TAKE",
                    subject_id=str(take.get("take_id", "")),
                    gate="RAW_VIDEO",
                    target_path=resolved,
                    statuses={"USER_APPROVED"},
                    require_current=True,
                )
            if (
                take is None
                or take.get("output_sha256") != expected
                or len(take_approvals) != 1
            ):
                errors.append(issue("E_UNAPPROVED_INPUT", f"Source is not bound to a USER_APPROVED take: {source.get('source_id')}"))


def _record_discovery_paths(root: Path, project: dict) -> list[Path]:
    return sorted(
        set(
            discover_approval_paths(root, project)
            + discover_asset_paths(root, project)
            + discover_shot_paths(root, project)
            + discover_take_paths(root, project)
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def _is_name_redirecting_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(getattr(metadata, "st_mode", 0)):
        return True
    return bool((getattr(metadata, "st_reparse_tag", 0) or 0) & 0x20000000)


def _fixed_history_dependency_paths(root: Path) -> list[Path]:
    """Discover fixed-authority history without following name redirections."""

    discovered: list[Path] = []
    raw_roots = [
        "01_story/history",
        "02_storyboard/history",
        "03_lookdev/history",
        "06_source_library/history",
    ]
    shots_root = root / "05_shots"
    if _is_name_redirecting_reparse(shots_root):
        raise ValueError("Shot dependency root is a name-redirecting reparse point")
    if shots_root.is_dir():
        try:
            shot_entries = list(os.scandir(shots_root))
        except OSError as exc:
            raise ValueError(f"Shot dependency root is unreadable: {exc}") from exc
        for entry in shot_entries:
            candidate = Path(entry.path)
            if _is_name_redirecting_reparse(candidate):
                raise ValueError(f"Shot dependency contains a name-redirecting reparse point: {candidate}")
            if (
                re.fullmatch(r"S\d{2,4}_SH\d{3,4}", entry.name) is not None
                and entry.is_dir(follow_symlinks=False)
            ):
                raw_roots.append(f"05_shots/{entry.name}/history")

    for raw_root in raw_roots:
        lexical_root = root.joinpath(*Path(raw_root).parts)
        lexical = root
        for part in Path(raw_root).parts:
            lexical /= part
            if _is_name_redirecting_reparse(lexical):
                raise ValueError(f"Fixed-history dependency contains a name-redirecting reparse point: {raw_root}")
        if not lexical_root.is_dir():
            continue
        pending = [lexical_root]
        while pending:
            directory = pending.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError as exc:
                raise ValueError(f"Fixed-history dependency is unreadable: {directory}: {exc}") from exc
            for entry in entries:
                candidate = Path(entry.path)
                if _is_name_redirecting_reparse(candidate):
                    raise ValueError(f"Fixed-history dependency contains a name-redirecting reparse point: {candidate}")
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(candidate)
                    elif entry.is_file(follow_symlinks=False):
                        discovered.append(candidate.resolve())
                except OSError as exc:
                    raise ValueError(f"Fixed-history dependency metadata is unavailable: {candidate}: {exc}") from exc
    return discovered


def _complete_dependency_discovery_paths(root: Path, project: dict) -> list[Path]:
    root = root.resolve()
    paths = set(_record_discovery_paths(root, project))
    configured_paths = project.get("paths") if isinstance(project.get("paths"), dict) else {}
    schema_root = safe_project_path(root, configured_paths.get("schemas", "00_schemas"))
    edit_root = safe_project_path(root, configured_paths.get("edit", "07_edit"))
    delivery_root = safe_project_path(root, configured_paths.get("delivery", "08_delivery"))
    candidates: list[Path] = []
    if schema_root.exists():
        candidates.extend(schema_root.rglob("*.json"))
    timeline_records = edit_root / "records"
    if timeline_records.exists():
        candidates.extend(timeline_records.rglob("timeline.json"))
    delivery_records = delivery_root / "records"
    if delivery_records.exists():
        candidates.extend(delivery_records.rglob("delivery.json"))
    candidates.extend(_fixed_history_dependency_paths(root))
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Preflight dependency escapes project root: {candidate}") from exc
        if resolved.is_file() and "_templates" not in candidate.parts:
            paths.add(resolved)
    return sorted(paths, key=lambda path: path.as_posix().casefold())


def _dependency_snapshot(
    root: Path,
    project: dict,
    records: list[tuple[dict, Path]],
    errors: list[dict],
) -> dict:
    root = root.resolve()
    paths: set[Path] = set()
    authority_defaults = {
        "story_contract": "01_story/STORY_CONTRACT.md",
        "storyboard": "02_storyboard/storyboard.json",
        "visual_bible": "03_lookdev/VISUAL_BIBLE.md",
        "asset_index": "04_assets/asset-index.json",
        "schema_manifest": "00_schemas/schema-manifest.json",
        "source_manifest": "06_source_library/source_manifest.json",
        "timeline": "07_edit/timeline.json",
        "delivery_record": "08_delivery/delivery.json",
    }
    for key, default in authority_defaults.items():
        try:
            paths.add(authority_path(root, project, key, default))
        except ValueError as exc:
            errors.append(issue("E_STAGE_PREREQ", f"Unsafe authority dependency: {exc}"))

    try:
        discovered = _complete_dependency_discovery_paths(root, project)
    except ValueError as exc:
        errors.append(issue("E_STAGE_PREREQ", f"Unsafe record dependency discovery: {exc}"))
        discovered = []
    paths.update(discovered)
    paths.update(path for _, path in records)

    def collect_payload_paths(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {
                    "path",
                    "output_file",
                    "source_file",
                    "image_file",
                    "authority_path",
                    "approval_record_path",
                } and isinstance(nested, str):
                    try:
                        paths.add(safe_project_path(root, nested))
                    except ValueError as exc:
                        errors.append(issue("E_STAGE_PREREQ", f"Unsafe dependency path: {exc}"))
                collect_payload_paths(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_payload_paths(nested)

    for record, _ in records:
        collect_payload_paths(record)
    for path in tuple(paths):
        if path.is_file() and path.suffix.casefold() == ".json":
            try:
                payload = read_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            collect_payload_paths(payload)

    file_items: list[dict] = []
    for path in sorted(paths, key=lambda item: item.as_posix().casefold()):
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except ValueError:
            errors.append(issue("E_STAGE_PREREQ", "Dependency escapes project root", path=str(path)))
            continue
        file_items.append(
            {
                "path": relative,
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    discovered_relpaths = [path.resolve().relative_to(root).as_posix() for path in discovered]
    snapshot = {"files": file_items, "record_paths": discovered_relpaths}
    snapshot["digest"] = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return snapshot


def _dependency_snapshot_matches(root: Path, snapshot: object) -> bool:
    if not isinstance(snapshot, dict):
        return False
    root = root.resolve()
    files = snapshot.get("files")
    expected_records = snapshot.get("record_paths")
    if not isinstance(files, list) or not isinstance(expected_records, list):
        return False
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return False
        try:
            path = safe_project_path(root, item["path"])
        except ValueError:
            return False
        actual = sha256_file(path) if path.is_file() else None
        if actual != item.get("sha256"):
            return False
    try:
        project = read_project(root)
        current_records = [
            path.resolve().relative_to(root).as_posix()
            for path in _complete_dependency_discovery_paths(root, project)
        ]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False
    return current_records == expected_records


def _evaluate_transition_impl(project_root: str | Path, gate: str, target_status: str) -> dict:
    """Evaluate a status change. Any missing proof denies the transition."""

    root = Path(project_root).expanduser().resolve()
    errors: list[dict] = []
    project_path = root / "project.json"
    if gate not in STAGES:
        return {**OFFLINE_VERIFICATION, "allowed": False, "errors": [issue("E_STAGE_PREREQ", f"Unknown gate: {gate}")]}
    try:
        project = read_project(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {**OFFLINE_VERIFICATION, "allowed": False, "errors": [issue("E_STAGE_PREREQ", str(exc), path=str(project_path))]}
    try:
        from validate_project import validate_project

        preflight = validate_project(root)
        if not preflight.get("ok", False):
            errors.extend(
                preflight.get("errors", [])
                or [issue("E_STAGE_PREREQ", "Full project validation failed without details")]
            )
    except Exception as exc:
        errors.append(issue("E_STAGE_PREREQ", f"Full project validation could not complete: {exc}"))
    if errors:
        return {**OFFLINE_VERIFICATION, "allowed": False, "errors": errors}
    gates = project.get("stage_gates") if isinstance(project, dict) else None
    if not isinstance(gates, dict):
        return {**OFFLINE_VERIFICATION, "allowed": False, "errors": [issue("E_STAGE_PREREQ", "project.stage_gates is missing")]}
    current = gates.get(gate)
    records: list[tuple[dict, Path]] = []
    try:
        records = _read_records(root, project)
    except ValueError as exc:
        errors.append(issue("E_STAGE_PREREQ", f"Unsafe record discovery path: {exc}"))
    project_id = project.get("project_id") if isinstance(project.get("project_id"), str) else ""
    active_ids = {
        item
        for item in project.get("active_approval_ids", [])
        if isinstance(item, str)
    } if isinstance(project.get("active_approval_ids"), list) else set()
    selected_approval: tuple[dict, Path] | None = None
    selected_approvals: list[tuple[dict, Path]] = []
    if current != target_status and target_status not in ALLOWED_TRANSITIONS.get(current, set()):
        errors.append(issue("E_STAGE_PREREQ", f"Illegal status transition for {gate}: {current} -> {target_status}"))
    if target_status == "USER_REVIEW_REQUIRED":
        index = STAGES.index(gate)
        for prerequisite in STAGES[:index]:
            if gates.get(prerequisite) != "USER_APPROVED":
                errors.append(issue("E_STAGE_PREREQ", f"{gate} review requires USER_APPROVED {prerequisite}"))
                continue
            if prerequisite in COLLECTION_GATES:
                _validate_collection_gate(
                    root,
                    project,
                    records,
                    prerequisite,
                    active_ids,
                    errors,
                    require_active=True,
                )
            else:
                prior_approval = _active_approval_for_gate(
                    records, prerequisite, project_id, active_ids, errors
                )
                if prior_approval is not None:
                    _check_approval(root, prior_approval, prerequisite, errors)
                    try:
                        _check_gate_authority(
                            root, project, records, prior_approval, prerequisite, errors
                        )
                    except ValueError as exc:
                        errors.append(issue("E_STAGE_PREREQ", f"Unsafe {prerequisite} authority target: {exc}"))
        if gate in COLLECTION_GATES:
            selected_approvals = _validate_collection_review_ready(
                root, project, records, gate, errors
            )
            selected_approval = selected_approvals[0] if selected_approvals else None
        else:
            candidates = _approval_candidates(
                records, gate, project_id, statuses=REVIEW_REQUEST_STATUS
            )
            if len(candidates) != 1:
                errors.append(
                    issue(
                        "E_UNAPPROVED_INPUT",
                        f"{gate} review requires exactly one current exact central review package",
                    )
                )
            else:
                selected_approval = candidates[0]
                selected_approvals = [selected_approval]
                if selected_approval[0].get("review_status") == "USER_APPROVED":
                    _check_approval(root, selected_approval, gate, errors)
                try:
                    _check_gate_authority(
                        root, project, records, selected_approval, gate, errors
                    )
                except ValueError as exc:
                    errors.append(issue("E_STAGE_PREREQ", f"Unsafe {gate} authority target: {exc}"))
    elif target_status == "USER_APPROVED":
        index = STAGES.index(gate)
        for prerequisite in STAGES[:index]:
            if gates.get(prerequisite) != "USER_APPROVED":
                errors.append(issue("E_STAGE_PREREQ", f"{gate} requires USER_APPROVED {prerequisite}"))
                continue
            if prerequisite in COLLECTION_GATES:
                _validate_collection_gate(
                    root,
                    project,
                    records,
                    prerequisite,
                    active_ids,
                    errors,
                    require_active=True,
                )
            else:
                prior_approval = _active_approval_for_gate(
                    records, prerequisite, project_id, active_ids, errors
                )
                if prior_approval is not None:
                    _check_approval(root, prior_approval, prerequisite, errors)
                    try:
                        _check_gate_authority(root, project, records, prior_approval, prerequisite, errors)
                    except ValueError as exc:
                        errors.append(issue("E_STAGE_PREREQ", f"Unsafe {prerequisite} authority target: {exc}"))
        if gate in COLLECTION_GATES:
            selected_approvals = _validate_collection_gate(
                root,
                project,
                records,
                gate,
                active_ids,
                errors,
                require_active=False,
            )
            selected_approval = selected_approvals[0] if selected_approvals else None
        else:
            candidates = _approval_candidates(records, gate, project_id)
            if len(candidates) != 1:
                errors.append(
                    issue(
                        "E_UNAPPROVED_INPUT",
                        f"{gate} requires exactly one concrete same-project USER_APPROVED approval record",
                    )
                )
            else:
                selected_approval = candidates[0]
                selected_approvals = [selected_approval]
                _check_approval(root, selected_approval, gate, errors)
                try:
                    _check_gate_authority(root, project, records, selected_approval, gate, errors)
                except ValueError as exc:
                    errors.append(issue("E_STAGE_PREREQ", f"Unsafe {gate} authority target: {exc}"))
        if gate in {"RAW_VIDEO", "SOURCE_LIBRARY"}:
            _check_video_proof(root, project, records, errors)
        if gate in {"EDIT", "FINISH"}:
            try:
                _check_source_library(root, project, records, errors)
            except ValueError as exc:
                errors.append(issue("E_SOURCE_LIBRARY_UNLOCKED", f"Unsafe source-library path: {exc}"))
        if gate in {"SHOT_STILL", "RAW_VIDEO", "SOURCE_LIBRARY"}:
            try:
                from validate_references import validate_references

                reference_result = validate_references(root)
                if not reference_result.get("ok", False):
                    errors.extend(reference_result.get("errors", []) or [issue("E_REFERENCE_ROLE_CONFLICT", "Reference validation failed without details")])
            except Exception as exc:
                errors.append(issue("E_REFERENCE_ROLE_CONFLICT", f"Reference validation could not complete: {exc}"))
        if gate in {"ASSET_LOCK", "SHOT_STILL", "RAW_VIDEO", "SOURCE_LIBRARY", "EDIT", "FINISH"}:
            try:
                from verify_lineage import verify_lineage

                lineage_result = verify_lineage(root)
                if not lineage_result.get("ok", False):
                    errors.extend(lineage_result.get("errors", []) or [issue("E_DERIVATIVE_AS_EDIT_BASE", "Lineage validation failed without details")])
            except Exception as exc:
                errors.append(issue("E_DERIVATIVE_AS_EDIT_BASE", f"Lineage validation could not complete: {exc}"))
    elif target_status == "REJECTED":
        if gate in COLLECTION_GATES:
            errors.append(
                issue(
                    "E_STAGE_PREREQ",
                    f"{gate} is a collection gate; an individual rejection must not reject the aggregate gate",
                )
            )
        else:
            candidates = _approval_candidates(
                records,
                gate,
                project_id,
                statuses=frozenset({"REJECTED"}),
            )
            if len(candidates) != 1:
                errors.append(
                    issue(
                        "E_UNAPPROVED_INPUT",
                        f"{gate} rejection requires exactly one current exact central REJECTED decision",
                    )
                )
            else:
                selected_approval = candidates[0]
                selected_approvals = [selected_approval]
                _check_approval(root, selected_approval, gate, errors)
                try:
                    _check_gate_authority(
                        root, project, records, selected_approval, gate, errors
                    )
                except ValueError as exc:
                    errors.append(
                        issue(
                            "E_STAGE_PREREQ",
                            f"Unsafe {gate} authority target: {exc}",
                        )
                    )
    elif target_status == "SUPERSEDED":
        index = STAGES.index(gate)
        for approved_gate in STAGES[: index + 1]:
            if gates.get(approved_gate) != "USER_APPROVED":
                errors.append(issue("E_STAGE_PREREQ", f"Cannot supersede {gate} while {approved_gate} is not USER_APPROVED"))
                continue
            if approved_gate in COLLECTION_GATES:
                collection_approvals = _validate_collection_gate(
                    root,
                    project,
                    records,
                    approved_gate,
                    active_ids,
                    errors,
                    require_active=True,
                )
                if approved_gate == gate:
                    selected_approvals = collection_approvals
                    selected_approval = collection_approvals[0] if collection_approvals else None
            else:
                active_approval = _active_approval_for_gate(
                    records, approved_gate, project_id, active_ids, errors
                )
                if active_approval is not None:
                    _check_approval(root, active_approval, approved_gate, errors)
                    try:
                        _check_gate_authority(root, project, records, active_approval, approved_gate, errors)
                    except ValueError as exc:
                        errors.append(issue("E_STAGE_PREREQ", f"Unsafe {approved_gate} authority target: {exc}"))
                    if approved_gate == gate:
                        selected_approval = active_approval
                        selected_approvals = [active_approval]

    dependency_snapshot = _dependency_snapshot(root, project, records, errors)
    approval_ids_by_gate = {
        stage: sorted(
            {
                str(record.get("approval_id"))
                for record, _ in records
                if record.get("gate") == stage and record.get("approval_id")
            }
        )
        for stage in STAGES
    }
    return {
        **OFFLINE_VERIFICATION,
        "allowed": not errors,
        "gate": gate,
        "current_status": current,
        "target_status": target_status,
        "selected_approval_id": selected_approval[0].get("approval_id") if selected_approval else None,
        "selected_approval_ids": sorted(
            str(item[0].get("approval_id")) for item in selected_approvals
        ),
        "approval_ids_by_gate": approval_ids_by_gate,
        "dependency_digest": dependency_snapshot["digest"],
        "dependencies": dependency_snapshot,
        "errors": errors,
    }


def evaluate_transition(project_root: str | Path, gate: str, target_status: str) -> dict:
    """Fail-closed public boundary for dry-run transition evaluation."""

    try:
        return _evaluate_transition_impl(project_root, gate, target_status)
    except Exception as exc:
        return {
            **OFFLINE_VERIFICATION,
            "allowed": False,
            "errors": [
                issue(
                    "E_STAGE_PREREQ",
                    f"Transition evaluation rejected malformed state ({type(exc).__name__}): {exc}",
                )
            ],
        }


def apply_transition(
    project_root: str | Path,
    gate: str,
    target_status: str,
    *,
    expected_project_sha256: str,
) -> dict:
    """Apply an allowed transition only when the caller proves the read version."""

    root = Path(project_root).expanduser().resolve()
    project_path = root / "project.json"
    try:
        with _transition_lock(root):
            if not project_path.is_file() or sha256_file(project_path).casefold() != expected_project_sha256.casefold():
                return {**OFFLINE_VERIFICATION, "allowed": False, "applied": False, "errors": [issue("E_APPROVAL_HASH_MISMATCH", "project.json changed since evaluation")]}
            result = evaluate_transition(root, gate, target_status)
            if not result["allowed"]:
                return {**result, "applied": False}
            # Re-evaluate every authority/evidence dependency immediately before
            # publication while the project transition lock is still held.
            first_result = result
            result = evaluate_transition(root, gate, target_status)
            if not result["allowed"]:
                return {**result, "applied": False}
            if first_result.get("dependency_digest") != result.get("dependency_digest"):
                return {
                    **result,
                    "allowed": False,
                    "applied": False,
                    "errors": [
                        issue(
                            "E_APPROVAL_HASH_MISMATCH",
                            "Transition authority/evidence dependencies changed during evaluation",
                        )
                    ],
                }
            if sha256_file(project_path).casefold() != expected_project_sha256.casefold():
                return {**OFFLINE_VERIFICATION, "allowed": False, "applied": False, "errors": [issue("E_APPROVAL_HASH_MISMATCH", "project.json changed during transition evaluation")]}
            project = read_json(project_path)
            project["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if target_status == "USER_APPROVED":
                project["stage_gates"][gate] = target_status
                approval_ids = {
                    item
                    for item in result.get("selected_approval_ids", [])
                    if isinstance(item, str)
                }
                active = project.get("active_approval_ids") if isinstance(project.get("active_approval_ids"), list) else []
                same_gate_ids = set(result.get("approval_ids_by_gate", {}).get(gate, []))
                active = [item for item in active if item not in same_gate_ids]
                project["active_approval_ids"] = sorted(set(active) | approval_ids)
                next_index = STAGES.index(gate) + 1
                project["current_stage"] = STAGES[next_index] if next_index < len(STAGES) else "COMPLETE"
                if gate == "FINISH":
                    project["project_status"] = "COMPLETED"
                    project["review_status"] = "USER_APPROVED"
            elif target_status == "SUPERSEDED":
                index = STAGES.index(gate)
                project["stage_gates"][gate] = "SUPERSEDED"
                for downstream in STAGES[index + 1 :]:
                    project["stage_gates"][downstream] = "DRAFT"
                invalidated_ids = {
                    approval_id
                    for affected_gate in STAGES[index:]
                    for approval_id in result.get("approval_ids_by_gate", {}).get(affected_gate, [])
                }
                active = project.get("active_approval_ids") if isinstance(project.get("active_approval_ids"), list) else []
                project["active_approval_ids"] = sorted(
                    approval_id for approval_id in set(active) if approval_id not in invalidated_ids
                )
                project["current_stage"] = gate
                project["project_status"] = "ACTIVE"
                project["review_status"] = "DRAFT"
            else:
                project["stage_gates"][gate] = target_status
                if target_status == "DRAFT":
                    project["current_stage"] = gate
                    project["project_status"] = "ACTIVE"
                    project["review_status"] = "DRAFT"
            staged: Path | None = None
            try:
                staged = _stage_project_json(project_path, project)
                staged_hash = sha256_file(staged)
                if sha256_file(project_path).casefold() != expected_project_sha256.casefold():
                    return {**OFFLINE_VERIFICATION, "allowed": False, "applied": False, "errors": [issue("E_APPROVAL_HASH_MISMATCH", "project.json changed before transition publication")]}
                if not _dependency_snapshot_matches(root, result.get("dependencies")):
                    return {
                        **result,
                        "allowed": False,
                        "applied": False,
                        "errors": [
                            issue(
                                "E_APPROVAL_HASH_MISMATCH",
                                "Transition authority/evidence dependencies changed before publication",
                            )
                        ],
                    }
                os.replace(staged, project_path)
                staged = None
                if not project_path.is_file() or sha256_file(project_path) != staged_hash:
                    return {
                        **result,
                        "allowed": False,
                        "applied": False,
                        "errors": [
                            issue(
                                "E_APPROVAL_HASH_MISMATCH",
                                "Published project bytes do not match the staged transition",
                            )
                        ],
                    }
                return {**result, "applied": True, "project_sha256": staged_hash}
            finally:
                if staged is not None:
                    staged.unlink(missing_ok=True)
    except TransitionLockBusy as exc:
        return {**OFFLINE_VERIFICATION, "allowed": False, "applied": False, "errors": [issue("E_STAGE_PREREQ", str(exc))]}
    except Exception as exc:
        return {
            **OFFLINE_VERIFICATION,
            "allowed": False,
            "applied": False,
            "errors": [
                issue(
                    "E_STAGE_PREREQ",
                    f"Transition application rejected malformed state ({type(exc).__name__}): {exc}",
                )
            ],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("gate", choices=STAGES)
    parser.add_argument("target_status", choices=tuple(ALLOWED_TRANSITIONS))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-project-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply:
        if not args.expected_project_sha256:
            result = {"allowed": False, "applied": False, "errors": [issue("E_APPROVAL_HASH_MISMATCH", "--apply requires --expected-project-sha256")]}
        else:
            result = apply_transition(args.project_root, args.gate, args.target_status, expected_project_sha256=args.expected_project_sha256)
    else:
        result = evaluate_transition(args.project_root, args.gate, args.target_status)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("allowed") and (not args.apply or result.get("applied")) else 1


if __name__ == "__main__":
    sys.exit(main())
