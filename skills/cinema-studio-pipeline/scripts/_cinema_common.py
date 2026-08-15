"""Shared, dependency-light helpers for Cinema Studio v2 command-line tools."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any, Iterable


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
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 250_000
_NAME_SURROGATE_BIT = 0x20000000
_SYMLINK_TAG = getattr(stat, "IO_REPARSE_TAG_SYMLINK", 0xA000000C)
_MOUNT_POINT_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def is_name_redirecting_reparse(path: str | Path) -> bool:
    """Detect symlink/junction/name-surrogate reparses, not cloud placeholders."""

    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    tag = int(getattr(metadata, "st_reparse_tag", 0) or 0)
    return tag in {_SYMLINK_TAG, _MOUNT_POINT_TAG} or bool(tag & _NAME_SURROGATE_BIT)


def contains_name_redirecting_component(path: str | Path) -> bool:
    """Walk an unresolved lexical path and reject any name-redirection component."""

    absolute = Path(path).expanduser()
    if not absolute.is_absolute():
        absolute = Path.cwd() / absolute
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if is_name_redirecting_reparse(current):
            return True
    return False


def read_json(path: Path) -> Any:
    with path.open("rb") as handle:
        encoded = handle.read(MAX_JSON_BYTES + 1)
    if len(encoded) > MAX_JSON_BYTES:
        raise json.JSONDecodeError("JSON file exceeds the safe size limit", "", 0)
    text = encoded.decode("utf-8-sig")
    def reject_nonstandard_constant(value: str) -> None:
        raise ValueError(f"Non-standard JSON numeric constant is forbidden: {value}")

    try:
        payload = json.loads(text, parse_constant=reject_nonstandard_constant)
    except json.JSONDecodeError:
        raise
    except RecursionError as exc:
        raise json.JSONDecodeError("JSON nesting exceeds the safe depth limit", text, 0) from exc
    except ValueError as exc:
        # Python can raise a plain ValueError for values such as integers beyond
        # sys.int_max_str_digits.  Present every malformed JSON value through the
        # same structured JSONDecodeError boundary used by callers.
        raise json.JSONDecodeError(f"Invalid JSON value: {exc}", text, 0) from exc

    stack: list[tuple[Any, int]] = [(payload, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > MAX_JSON_DEPTH:
            raise json.JSONDecodeError("JSON nesting exceeds the safe depth limit", text, 0)
        if nodes > MAX_JSON_NODES:
            raise json.JSONDecodeError("JSON document exceeds the safe node limit", text, 0)
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise json.JSONDecodeError("JSON numbers must be finite", text, 0)
    return payload


def json_bytes(payload: Any) -> bytes:
    """Return the one canonical on-disk JSON representation used by writers."""

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json(path: Path, payload: Any, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        commit_temporary_file(temporary, path, force=force)
    finally:
        temporary.unlink(missing_ok=True)


def commit_temporary_file(temporary: Path, target: Path, *, force: bool) -> None:
    """Publish a sibling temporary atomically, with create-only semantics by default."""

    try:
        if force:
            os.replace(temporary, target)
        else:
            # A same-directory hard link is an atomic create-if-absent. Unlike
            # replace(), it cannot overwrite a file created after preflight.
            os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def canonical_relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def issue(code: str, message: str, *, path: str | None = None, **details: Any) -> dict:
    result = {"code": code, "message": message}
    if path is not None:
        result["path"] = path
    if details:
        result["details"] = details
    return result


def offline_remote_package_error(path: Path, record: dict, *, record_type: str) -> str | None:
    """Check a hashed JSON evidence package for offline record consistency only."""

    if path.suffix.casefold() != ".json":
        return "remote evidence package must be JSON"
    try:
        package = read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return f"remote evidence package is unreadable: {exc}"
    if not isinstance(package, dict) or package.get("verification_scope") != "OFFLINE_RECORD_CONSISTENCY":
        return "remote evidence package must declare OFFLINE_RECORD_CONSISTENCY"
    remote = record.get("remote") if isinstance(record.get("remote"), dict) else {}
    expected: dict[str, Any] = {"provider": remote.get("provider")}
    if record_type == "TAKE":
        model = record.get("model") if isinstance(record.get("model"), dict) else {}
        expected.update(
            {
                "project_id": remote.get("project_id"),
                "job_id": remote.get("job_id"),
                "model_name": model.get("name"),
                "output_sha256": record.get("output_sha256"),
            }
        )
    else:
        lineage = record.get("lineage") if isinstance(record.get("lineage"), dict) else {}
        expected.update(
            {
                "project_id": remote.get("remote_project_id"),
                "asset_id": remote.get("remote_asset_id"),
                "output_sha256": lineage.get("output_sha256"),
            }
        )
    missing_or_mismatched = [
        key for key, expected_value in expected.items()
        if not expected_value or package.get(key) != expected_value
    ]
    if missing_or_mismatched:
        return "remote evidence package does not bind: " + ", ".join(missing_or_mismatched)
    return None


def record_id(record: dict) -> str | None:
    # Prefer the most-specific record identifier. A take also carries shot_id,
    # so choosing shot_id first would collapse every take into its parent shot.
    for key in (
        "take_id",
        "shot_id",
        "asset_id",
        "source_id",
        "delivery_id",
        "timeline_id",
        "storyboard_id",
        "library_id",
        "approval_id",
        "id",
    ):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def iter_json_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    return sorted(
        (path for path in root.rglob("*.json") if path.is_file()),
        key=lambda item: item.as_posix().casefold(),
    )


def read_project(root: Path) -> dict:
    payload = read_json(root / "project.json")
    if not isinstance(payload, dict):
        raise ValueError("project.json must contain an object")
    return payload


def authority_path(
    root: Path,
    project: dict,
    key: str,
    default: str,
) -> Path:
    authority = project.get("authority_files")
    raw_path = authority.get(key) if isinstance(authority, dict) else None
    return safe_project_path(root, raw_path if isinstance(raw_path, str) else default)


def project_path(root: Path, project: dict, key: str, default: str) -> Path:
    paths = project.get("paths")
    raw_path = paths.get(key) if isinstance(paths, dict) else None
    return safe_project_path(root, raw_path if isinstance(raw_path, str) else default)


def safe_project_path(root: Path, raw_path: str | Path) -> Path:
    if not isinstance(raw_path, (str, Path)):
        raise ValueError(f"Project-relative path is invalid: {raw_path!r}")
    raw_text = os.fspath(raw_path)
    path = Path(raw_path)
    if (
        not raw_text
        or path.is_absolute()
        or bool(path.drive)
        or re.match(r"^[A-Za-z]:", raw_text) is not None
        or ".." in path.parts
    ):
        raise ValueError(f"Project-relative path is unsafe: {raw_path}")
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Project-relative path escapes root: {raw_path}") from exc
    return resolved


def find_bound_approvals(
    root: Path,
    approvals: Iterable[tuple[dict, Path]],
    *,
    project_id: str,
    subject_type: str,
    subject_id: str,
    gate: str,
    target_path: Path,
    statuses: set[str] | frozenset[str],
    require_current: bool,
) -> list[tuple[dict, Path]]:
    """Return central approvals that bind one exact in-project authority artifact."""

    resolved_root = root.resolve()
    resolved_target = target_path.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        return []
    if not resolved_target.is_file():
        return []
    try:
        target_hash = sha256_file(resolved_target)
    except OSError:
        return []
    matched: list[tuple[dict, Path]] = []
    for approval, approval_path in approvals:
        if (
            approval.get("project_id") != project_id
            or approval.get("subject_type") != subject_type
            or approval.get("subject_id") != subject_id
            or approval.get("gate") != gate
            or approval.get("subject_sha256") != target_hash
            or approval.get("review_status") not in statuses
            or (require_current and approval.get("superseded_by_approval_id") is not None)
        ):
            continue
        evidence_matches = False
        for item in approval.get("evidence", []) if isinstance(approval.get("evidence"), list) else []:
            if (
                not isinstance(item, dict)
                or item.get("sha256") != target_hash
                or not isinstance(item.get("path"), str)
            ):
                continue
            try:
                evidence_path = safe_project_path(resolved_root, item["path"])
            except ValueError:
                continue
            if evidence_path == resolved_target:
                evidence_matches = True
                break
        if evidence_matches:
            matched.append((approval, approval_path))
    return matched


def _record_paths_from_index(index_path: Path, root: Path) -> list[Path]:
    if not index_path.is_file():
        return []
    try:
        index = read_json(index_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    records = index.get("records", []) if isinstance(index, dict) else []
    paths: list[Path] = []
    for record in records if isinstance(records, list) else []:
        raw_path = record.get("path") if isinstance(record, dict) else record
        if isinstance(raw_path, str):
            paths.append(safe_project_path(root, raw_path))
    return paths


def _contained_discovered_paths(
    candidates: Iterable[Path], project_root: Path, *, records_root: Path | None = None
) -> list[Path]:
    resolved_root = project_root.resolve()
    resolved_records_root = records_root.resolve() if records_root is not None else None
    safe: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(resolved_root)
            if resolved_records_root is not None:
                resolved.relative_to(resolved_records_root)
        except ValueError as exc:
            raise ValueError(f"Discovered record escapes its project authority root: {candidate}") from exc
        if resolved.is_file():
            safe.append(resolved)
    return safe


def discover_asset_paths(root: Path, project: dict) -> list[Path]:
    records_root = authority_path(root, project, "asset_records_root", "04_assets/records")
    index_path = authority_path(root, project, "asset_index", "04_assets/asset-index.json")
    candidates = _record_paths_from_index(index_path, root)
    if records_root.exists():
        candidates.extend(records_root.rglob("asset.json"))
    return sorted(
        set(_contained_discovered_paths(candidates, root, records_root=records_root)),
        key=lambda path: path.as_posix().casefold(),
    )


def discover_shot_paths(root: Path, project: dict) -> list[Path]:
    shots_root = project_path(root, project, "shots", "05_shots")
    return sorted(
        _contained_discovered_paths(
            (
                path
                for path in shots_root.glob("*/shot.json")
                if re.fullmatch(r"S\d{2,4}_SH\d{3,4}", path.parent.name) is not None
            ),
            root,
            records_root=shots_root,
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def discover_take_paths(root: Path, project: dict) -> list[Path]:
    shots_root = project_path(root, project, "shots", "05_shots")
    return sorted(
        _contained_discovered_paths(
            (
                path
                for path in shots_root.glob("*/takes/*/take.json")
                if re.fullmatch(r"S\d{2,4}_SH\d{3,4}", path.parents[2].name) is not None
                and re.fullmatch(r"S\d{2,4}_SH\d{3,4}_T\d{2,3}", path.parent.name) is not None
            ),
            root,
            records_root=shots_root,
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def discover_approval_paths(root: Path, project: dict) -> list[Path]:
    approvals_root = project_path(root, project, "approvals", "09_approvals")
    return sorted(
        _contained_discovered_paths(
            (
                path
                for path in approvals_root.rglob("*.json")
                if "_templates" not in path.parts
            ),
            root,
            records_root=approvals_root,
        ),
        key=lambda path: path.as_posix().casefold(),
    )
