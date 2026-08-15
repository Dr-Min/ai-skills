#!/usr/bin/env python3
"""Read-only audit for duplicate Cinema Studio skill installations and wrappers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from _cinema_common import issue


SKILL_NAME = "cinema-studio-pipeline"
CANONICAL_MARKER = re.compile(r"Canonical skill:\s*`([^`]+)`", re.IGNORECASE)


def _normalized_wrapper_text(text: str) -> str:
    """Normalize only transport details; wrapper content remains exact."""

    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def _expected_wrapper_text(canonical_root: Path) -> str:
    canonical_dir = canonical_root.resolve().as_posix()
    canonical_skill = f"{canonical_dir}/SKILL.md"
    return (
        "---\n"
        "name: cinema-studio-pipeline\n"
        "description: >-\n"
        "  Compatibility entrypoint for the canonical Cinema Studio Pipeline v2. Use for\n"
        "  Higgsfield and Seedance filmmaking, approved storyboards and assets, JSON-driven\n"
        "  shots, immutable sources, music-aware editing, QA, and delivery. Delegate every task\n"
        f"  to the canonical skill at {canonical_dir}.\n"
        "---\n\n"
        "# Cinema Studio Pipeline compatibility entrypoint\n\n"
        "Treat this folder as a non-operational compatibility shim.\n\n"
        f"Canonical skill: `{canonical_skill}`\n\n"
        "1. Open and read the complete canonical instructions at\n"
        f"   `{canonical_skill}`.\n"
        "2. Resolve every workflow, schema, template, provider rule, integration, reference,\n"
        "   and script relative to that canonical directory.\n"
        "3. Follow the canonical instructions exactly; do not merge them with this folder's\n"
        "   legacy references.\n"
        "4. If the canonical `SKILL.md` or any required canonical resource is unavailable,\n"
        "   stop and report the missing path. Do not fall back to legacy rules.\n\n"
        "The files under this folder's `references/` are preserved only for compatibility and\n"
        "historical provenance. They are `LEGACY / DO NOT ROUTE`.\n"
    )


def _frontmatter_name(text: str) -> str | None:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"\s*name\s*:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip(" '\"")
    return None


def _same_path(left: Path, right: Path) -> bool:
    return str(left.resolve()).replace("\\", "/").casefold() == str(right.resolve()).replace("\\", "/").casefold()


def validate_install(
    canonical_root: str | Path | None = None,
    *,
    candidate_roots: Iterable[str | Path] | None = None,
) -> dict:
    """Classify same-name installs; never delete, move, or rewrite them."""

    canonical = (
        Path(canonical_root).expanduser().resolve()
        if canonical_root is not None
        else Path(__file__).resolve().parents[1]
    )
    if candidate_roots is None:
        user_home = Path.home()
        candidates = [
            canonical,
            user_home / ".agents" / "skills" / SKILL_NAME,
            user_home / ".claude" / "skills" / SKILL_NAME,
        ]
    else:
        candidates = [Path(path).expanduser().resolve() for path in candidate_roots]
    errors: list[dict] = []
    locations: list[dict] = []
    canonical_skill = canonical / "SKILL.md"
    if not canonical_skill.is_file():
        errors.append(issue("CANONICAL_MISSING", f"Canonical SKILL.md not found: {canonical_skill}"))
        canonical_text = ""
    else:
        canonical_text = canonical_skill.read_text(encoding="utf-8-sig")
        if _frontmatter_name(canonical_text) != SKILL_NAME:
            errors.append(issue("CANONICAL_NAME_MISMATCH", f"Canonical frontmatter name must be {SKILL_NAME}", path=str(canonical_skill)))
    seen: set[str] = set()
    for candidate in candidates:
        resolved_key = str(candidate.resolve()).replace("\\", "/").casefold()
        if resolved_key in seen or not candidate.exists():
            continue
        seen.add(resolved_key)
        skill_file = candidate / "SKILL.md"
        entry = {"path": str(candidate), "skill_file": str(skill_file)}
        if _same_path(candidate, canonical):
            entry["classification"] = "CANONICAL"
            locations.append(entry)
            continue
        if not skill_file.is_file():
            entry["classification"] = "INVALID_DUPLICATE"
            errors.append(issue("DUPLICATE_ACTIVE_SKILL", f"Same-name directory has no SKILL.md: {candidate}", path=str(candidate)))
            locations.append(entry)
            continue
        try:
            text = skill_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            entry["classification"] = "INVALID_DUPLICATE"
            errors.append(issue("DUPLICATE_ACTIVE_SKILL", str(exc), path=str(skill_file)))
            locations.append(entry)
            continue
        if _frontmatter_name(text) != SKILL_NAME:
            entry["classification"] = "INVALID_DUPLICATE"
            errors.append(issue("WRAPPER_NAME_MISMATCH", f"Wrapper frontmatter name must be {SKILL_NAME}", path=str(skill_file)))
            locations.append(entry)
            continue
        marker = CANONICAL_MARKER.search(text)
        if marker is None:
            entry["classification"] = "ACTIVE_DUPLICATE"
            errors.append(issue("DUPLICATE_ACTIVE_SKILL", f"Duplicate is not a fail-closed compatibility wrapper: {candidate}", path=str(skill_file)))
            locations.append(entry)
            continue
        declared = Path(marker.group(1)).expanduser()
        expected = canonical_skill.resolve()
        if not _same_path(declared, expected):
            entry["classification"] = "INVALID_WRAPPER"
            entry["declared_target"] = str(declared)
            errors.append(issue("WRAPPER_TARGET_MISMATCH", f"Wrapper target must be {expected}", path=str(skill_file), declared_target=str(declared)))
        elif not expected.is_file():
            entry["classification"] = "INVALID_WRAPPER"
            errors.append(issue("CANONICAL_MISSING", f"Wrapper target does not exist: {expected}", path=str(skill_file)))
        elif _normalized_wrapper_text(text) != _normalized_wrapper_text(_expected_wrapper_text(canonical)):
            entry["classification"] = "ACTIVE_DUPLICATE"
            errors.append(
                issue(
                    "DUPLICATE_ACTIVE_SKILL",
                    f"Duplicate does not exactly match the approved compatibility wrapper: {candidate}",
                    path=str(skill_file),
                )
            )
        else:
            entry["classification"] = "VALID_WRAPPER"
            entry["declared_target"] = str(expected)
        locations.append(entry)
    return {"ok": not errors, "canonical": str(canonical), "locations": locations, "errors": errors}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--candidate", action="append", type=Path, dest="candidates")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_install(args.canonical, candidate_roots=args.candidates)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
