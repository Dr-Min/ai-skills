#!/usr/bin/env python3
"""Record one explicit user approval or rejection for a prepared central review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _cinema_common import (
    canonical_relpath,
    discover_approval_paths,
    issue,
    json_bytes,
    project_path,
    read_json,
    read_project,
    safe_project_path,
    sha256_file,
)
from decision_receipts import issue_decision_receipt
from prepare_review import OFFLINE, SUBJECT_GATES, _authority, _supporting_evidence
from prepare_review import _assert_safe_write_target, _lexical_project_path, _validate_approval_candidate
from transition_status import COLLECTION_GATES, _transition_lock
from validate_project import validate_review_candidate


def _result(*, allowed: bool, errors: list[dict], **values: object) -> dict:
    return {**OFFLINE, "allowed": allowed, "decision_recorded": False, "gate_activated": False, "errors": errors, **values}


def _atomic_replace_json(root: Path, path: Path, payload: dict, expected_sha256: str) -> None:
    """Replace only the caller-observed approval bytes with a durable new record."""
    _assert_safe_write_target(root, path)
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("Approval changed before publication")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(path) != expected_sha256:
            raise ValueError("Approval changed during publication")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _find_approval(root: Path, project: dict, approval_id: str) -> tuple[dict, Path]:
    found: list[tuple[dict, Path]] = []
    for path in discover_approval_paths(root, project):
        try:
            approval = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Central approval record is unreadable: {path}") from exc
        if not isinstance(approval, dict):
            raise ValueError(f"Central approval record must contain an object: {path}")
        if approval.get("approval_id") == approval_id:
            found.append((approval, path))
    if len(found) != 1:
        raise ValueError("Approval id must resolve to exactly one central approval record")
    paths = project.get("paths") if isinstance(project.get("paths"), dict) else {}
    raw_root = paths.get("approvals", "09_approvals")
    if not isinstance(raw_root, str):
        raise ValueError("Project approvals path is invalid")
    lexical = _lexical_project_path(root, f"{raw_root}/{approval_id}.json")
    if found[0][1].resolve() != lexical.resolve():
        raise ValueError("Approval record is not the canonical central approval target")
    _assert_safe_write_target(root, lexical)
    return found[0][0], lexical


def _verify_evidence(root: Path, approval: dict) -> None:
    evidence = approval.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Prepared approval has no evidence")
    subject_bound = False
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise ValueError("Approval evidence is incomplete")
        path = safe_project_path(root, item["path"])
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise ValueError(f"Approval evidence bytes mismatch: {item['path']}")
        subject_bound = subject_bound or item["sha256"] == approval.get("subject_sha256")
    if not subject_bound:
        raise ValueError("Approval evidence does not bind subject_sha256")


def _validate_decision_contract(root: Path, project: dict, approval: dict, approval_path: Path) -> Path:
    """Revalidate decision authority, current target, and immutable fixed archives."""
    subject_type, subject_id = approval.get("subject_type"), approval.get("subject_id")
    if subject_type not in SUBJECT_GATES or not isinstance(subject_id, str):
        raise ValueError("Approval subject is unsupported")
    if approval.get("gate") != SUBJECT_GATES[subject_type]:
        raise ValueError("Approval gate does not match its subject type")
    authority, record = _authority(root, project, subject_type, subject_id)
    current_pair = (canonical_relpath(authority, root), sha256_file(authority))
    if approval.get("subject_sha256") != current_pair[1]:
        raise ValueError("Approval subject hash is no longer bound to the current authority")
    evidence = approval.get("evidence", []) if isinstance(approval.get("evidence"), list) else []
    if not any(
        isinstance(item, dict) and (item.get("path"), item.get("sha256")) == current_pair
        for item in evidence
    ):
        raise ValueError("Approval omits the exact current authority evidence")
    mandatory = [(authority, "Current content authority")] + _supporting_evidence(
        root, project, subject_type, record, ()
    )
    actual_pairs = {
        (item.get("path"), item.get("sha256"))
        for item in evidence
        if isinstance(item, dict)
    }
    missing = [
        canonical_relpath(path, root)
        for path, _ in mandatory
        if (canonical_relpath(path, root), sha256_file(path)) not in actual_pairs
    ]
    if missing:
        raise ValueError(f"Approval omits mandatory current evidence: {', '.join(sorted(missing))}")
    _verify_evidence(root, approval)
    _validate_approval_candidate(root, project, approval)
    from validate_project import _check_fixed_approval_archives
    approvals = []
    for path in discover_approval_paths(root, project):
        try:
            candidate = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(candidate, dict):
            approvals.append((candidate, path))
    errors: list[dict] = []
    _check_fixed_approval_archives(root, {"approvals": approvals}, errors)
    if errors:
        raise ValueError(f"Fixed authority archive contract failed: {errors[0]['message']}")
    return authority


def record_decision(project_root: str | Path, approval_id: str, decision: str, *, actor: str, reference: str | None, notes: str | None, expected_project_sha256: str, expected_approval_sha256: str, expected_subject_sha256: str, apply: bool = False) -> dict:
    root = Path(project_root).expanduser().resolve()
    if decision not in {"approve", "reject"}:
        return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "decision must be approve or reject")])
    try:
        project = read_project(root)
        project_file = root / "project.json"
        approval, approval_path = _find_approval(root, project, approval_id)
        if approval.get("project_id") != project.get("project_id"):
            raise ValueError("Approval belongs to another project")
        if approval.get("review_status") != "USER_REVIEW_REQUIRED":
            raise ValueError("Only USER_REVIEW_REQUIRED approvals can receive a decision")
        authority = _validate_decision_contract(root, project, approval, approval_path)
        pending_report = validate_review_candidate(
            root,
            str(approval.get("subject_type", "")),
            str(approval.get("subject_id", "")),
            approval,
        )
        if not pending_report.get("ok"):
            return _result(
                allowed=False,
                errors=pending_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Pending review validation failed")]),
            )
        if (sha256_file(project_file) != expected_project_sha256 or sha256_file(approval_path) != expected_approval_sha256 or sha256_file(authority) != expected_subject_sha256 or approval.get("subject_sha256") != expected_subject_sha256):
            return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Project, approval, or subject changed since caller evaluation")])
        if not actor or (decision == "approve" and not reference) or (decision == "reject" and not notes):
            raise ValueError("actor, approval reference, and rejection notes are required")
        updated = dict(approval)
        updated["review_status"] = "USER_APPROVED" if decision == "approve" else "REJECTED"
        updated["decided_by_type"] = "USER"
        updated["decided_by"] = actor
        updated["decided_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if reference:
            updated["user_evidence_reference"] = reference
        if notes:
            updated["decision_notes"] = notes
        _validate_approval_candidate(root, project, updated)
        updated_report = validate_review_candidate(
            root,
            str(updated.get("subject_type", "")),
            str(updated.get("subject_id", "")),
            updated,
        )
        if not updated_report.get("ok"):
            return _result(
                allowed=False,
                errors=updated_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Decision validation failed")]),
            )
    except Exception as exc:
        return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", str(exc))])
    result = _result(allowed=True, errors=[], approval_id=approval_id, approval_path=canonical_relpath(approval_path, root))
    if not apply:
        return result
    try:
        # The transition lock gives an inter-process CAS boundary for the decision write.
        with _transition_lock(root):
            if sha256_file(project_file) != expected_project_sha256 or sha256_file(approval_path) != expected_approval_sha256:
                return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Project or subject changed before decision publication")])
            approval = read_json(approval_path)
            authority = _validate_decision_contract(root, project, approval, approval_path)
            if sha256_file(authority) != expected_subject_sha256:
                return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", "Subject changed before decision publication")])
            pending_report = validate_review_candidate(
                root,
                str(approval.get("subject_type", "")),
                str(approval.get("subject_id", "")),
                approval,
            )
            if not pending_report.get("ok"):
                return _result(
                    allowed=False,
                    errors=pending_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Pending review validation failed inside decision lock")]),
                )
            _validate_approval_candidate(root, project, updated)
            updated_report = validate_review_candidate(
                root,
                str(updated.get("subject_type", "")),
                str(updated.get("subject_id", "")),
                updated,
            )
            if not updated_report.get("ok"):
                return _result(
                    allowed=False,
                    errors=updated_report.get("errors", [issue("E_UNAPPROVED_INPUT", "Decision validation failed inside decision lock")]),
                )
            receipt = issue_decision_receipt(
                root, str(project.get("project_id", "")), updated, approval_path
            )
            if receipt.get("approval_sha256") != hashlib.sha256(json_bytes(updated)).hexdigest():
                raise ValueError("Decision receipt does not bind the final approval bytes")
            _atomic_replace_json(root, approval_path, updated, expected_approval_sha256)
        result["decision_recorded"] = True
    except Exception as exc:
        return _result(allowed=False, errors=[issue("E_APPROVAL_HASH_MISMATCH", str(exc))])
    if decision == "approve" or (decision == "reject" and approval["gate"] not in COLLECTION_GATES):
        try:
            from transition_status import apply_transition
            target_status = "USER_APPROVED" if decision == "approve" else "REJECTED"
            transition = apply_transition(root, approval["gate"], target_status, expected_project_sha256=expected_project_sha256)
            result["gate_activated"] = bool(transition.get("applied"))
            result["gate_transition"] = transition
        except Exception as exc:  # Preserve the explicit user decision; no rollback.
            result["gate_transition"] = {"allowed": False, "applied": False, "errors": [issue("E_STAGE_PREREQ", str(exc))]}
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("approval_id")
    parser.add_argument("decision", choices=("approve", "reject"))
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reference")
    parser.add_argument("--notes")
    parser.add_argument("--expected-project-sha256", required=True)
    parser.add_argument("--expected-approval-sha256", required=True)
    parser.add_argument("--expected-subject-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = record_decision(args.project_root, args.approval_id, args.decision, actor=args.actor, reference=args.reference, notes=args.notes, expected_project_sha256=args.expected_project_sha256, expected_approval_sha256=args.expected_approval_sha256, expected_subject_sha256=args.expected_subject_sha256, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("allowed") or (args.apply and not result.get("decision_recorded")):
        return 1
    return 2 if args.apply and not result.get("gate_activated") else 0


if __name__ == "__main__":
    sys.exit(main())
