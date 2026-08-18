#!/usr/bin/env python3
"""Machine-local HMAC receipts for explicit central approval decisions."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
import uuid
from pathlib import Path

from _cinema_common import json_bytes, read_json, sha256_file


RECEIPT_STATUSES = frozenset({"USER_APPROVED", "REJECTED"})
_NAME_SURROGATE_BIT = 0x20000000
_SYMLINK_TAG = getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def receipt_store_root() -> Path:
    """Return the fixed per-user state location; project data never controls it."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    if not base.is_absolute():
        raise ValueError("Machine-local decision receipt base must be absolute")
    return base / "OpenAI" / "Codex" / "cinema-studio-pipeline" / "decision-receipts"


def _name_redirecting(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    tag = int(getattr(metadata, "st_reparse_tag", 0) or 0)
    return tag in {_SYMLINK_TAG, _MOUNT_POINT_TAG} or bool(tag & _NAME_SURROGATE_BIT)


def _assert_safe_components(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("Decision receipt path must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if _name_redirecting(current):
                raise ValueError(f"Decision receipt path contains a name-redirection: {current}")


def _assert_not_project_controlled(store: Path, project_root: Path) -> None:
    resolved_store = store.resolve(strict=False)
    resolved_project = project_root.resolve()
    try:
        resolved_store.relative_to(resolved_project)
    except ValueError:
        return
    raise ValueError("Decision receipt store must be outside the project")


def _ensure_private_directory(path: Path) -> None:
    _assert_safe_components(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _assert_safe_components(path)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _assert_single_link_file(path: Path, label: str) -> None:
    _assert_safe_components(path)
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} is not a regular file")
    if getattr(metadata, "st_nlink", 1) != 1:
        raise ValueError(f"{label} has a hardlink alias")


def _create_only_bytes(path: Path, payload: bytes, mode: int) -> bool:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            return False
    finally:
        temporary.unlink(missing_ok=True)


def _load_or_create_key(store: Path) -> bytes:
    _ensure_private_directory(store)
    key_path = store / "hmac.key"
    _assert_safe_components(key_path)
    if not key_path.exists():
        _create_only_bytes(key_path, secrets.token_bytes(32), 0o600)
    _assert_single_link_file(key_path, "Decision receipt HMAC key")
    key = key_path.read_bytes()
    if len(key) != 32:
        raise ValueError("Decision receipt HMAC key has an invalid length")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def _read_key(store: Path) -> bytes:
    key_path = store / "hmac.key"
    if not key_path.is_file():
        raise ValueError("Decision receipt HMAC key is missing")
    _assert_single_link_file(key_path, "Decision receipt HMAC key")
    key = key_path.read_bytes()
    if len(key) != 32:
        raise ValueError("Decision receipt HMAC key has an invalid length")
    return key


def _normalized_root(project_root: Path) -> str:
    value = str(project_root.resolve())
    return value.casefold() if os.name == "nt" else value


def _evidence_digest(approval: dict) -> str:
    normalized = sorted(
        (
            {
                "path": item.get("path"),
                "sha256": item.get("sha256"),
                "verified_claim": item.get("verified_claim"),
            }
            for item in approval.get("evidence", [])
            if isinstance(item, dict)
        ),
        key=lambda item: (
            str(item.get("path")),
            str(item.get("sha256")),
            str(item.get("verified_claim")),
        ),
    )
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approval_relative_path(project_root: Path, approval_path: str | Path) -> str:
    lexical = Path(approval_path).expanduser()
    if not lexical.is_absolute():
        lexical = project_root / lexical
    lexical = lexical.absolute()
    _assert_safe_components(lexical)
    resolved = lexical.resolve(strict=False)
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Central approval path escapes the project") from exc


def _claims(
    project_root: Path,
    project_id: str,
    approval: dict,
    approval_path: str | Path,
) -> dict:
    approval_bytes = json_bytes(approval)
    return {
        "receipt_version": 1,
        "canonical_project_root": _normalized_root(project_root),
        "project_id": project_id,
        "approval_id": approval.get("approval_id"),
        "approval_path": _approval_relative_path(project_root, approval_path),
        "subject_type": approval.get("subject_type"),
        "subject_id": approval.get("subject_id"),
        "gate": approval.get("gate"),
        "review_status": approval.get("review_status"),
        "decided_at": approval.get("decided_at"),
        "approval_sha256": hashlib.sha256(approval_bytes).hexdigest(),
        "subject_sha256": approval.get("subject_sha256"),
        "evidence_digest": _evidence_digest(approval),
    }


def _claims_hmac(key: bytes, claims: dict) -> str:
    encoded = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _receipt_path(store: Path, claims: dict) -> Path:
    root_digest = hashlib.sha256(str(claims["canonical_project_root"]).encode("utf-8")).hexdigest()
    return store / "receipts" / root_digest / f"{claims['approval_sha256']}.json"


def preview_decision_receipt(
    project_root: str | Path,
    project_id: str,
    approval: dict,
    approval_path: str | Path,
) -> dict:
    root = Path(project_root).expanduser().resolve()
    if approval.get("review_status") not in RECEIPT_STATUSES:
        raise ValueError("Only USER_APPROVED or REJECTED decisions receive receipts")
    claims = _claims(root, project_id, approval, approval_path)
    return {"approval_sha256": claims["approval_sha256"], "claims": claims}


def issue_decision_receipt(
    project_root: str | Path,
    project_id: str,
    approval: dict,
    approval_path: str | Path,
) -> dict:
    root = Path(project_root).expanduser().resolve()
    preview = preview_decision_receipt(root, project_id, approval, approval_path)
    claims = preview["claims"]
    store = receipt_store_root().expanduser()
    if not store.is_absolute():
        raise ValueError("Decision receipt store must be absolute")
    _assert_not_project_controlled(store, root)
    key = _load_or_create_key(store)
    receipt_path = _receipt_path(store, claims)
    _ensure_private_directory(receipt_path.parent)
    receipt = {"claims": claims, "hmac_sha256": _claims_hmac(key, claims)}
    created = _create_only_bytes(receipt_path, json_bytes(receipt), 0o600)
    _assert_single_link_file(receipt_path, "Decision receipt")
    if not created:
        existing = read_json(receipt_path)
        if existing != receipt:
            raise ValueError("Existing decision receipt does not match the final approval")
    return {
        "approval_sha256": claims["approval_sha256"],
        "receipt_path": str(receipt_path),
    }


def verify_decision_receipt(
    project_root: str | Path,
    project_id: str,
    approval: dict,
    approval_path: str | Path,
) -> str | None:
    try:
        root = Path(project_root).expanduser().resolve()
        path = Path(approval_path).expanduser().absolute()
        if approval.get("review_status") not in RECEIPT_STATUSES:
            return None
        _assert_single_link_file(path, "Central approval record")
        claims = _claims(root, project_id, approval, path)
        if sha256_file(path) != claims["approval_sha256"]:
            raise ValueError("Central approval bytes do not match canonical receipt claims")
        store = receipt_store_root().expanduser()
        if not store.is_absolute():
            raise ValueError("Decision receipt store must be absolute")
        _assert_not_project_controlled(store, root)
        _assert_safe_components(store)
        key = _read_key(store)
        receipt_path = _receipt_path(store, claims)
        if not receipt_path.is_file():
            raise ValueError("Decision receipt is missing")
        _assert_single_link_file(receipt_path, "Decision receipt")
        receipt = read_json(receipt_path)
        if not isinstance(receipt, dict) or receipt.get("claims") != claims:
            raise ValueError("Decision receipt claims do not match the approval")
        actual_hmac = receipt.get("hmac_sha256")
        expected_hmac = _claims_hmac(key, claims)
        if not isinstance(actual_hmac, str) or not hmac.compare_digest(actual_hmac, expected_hmac):
            raise ValueError("Decision receipt HMAC is invalid")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return str(exc)
