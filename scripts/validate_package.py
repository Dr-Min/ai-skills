#!/usr/bin/env python3
"""Fast, dependency-free package integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SKILLS = {
    "biz-ai-secretary",
    "biz-color-map",
    "biz-finance-team",
    "biz-health-check",
    "biz-legal-team",
    "biz-monthly-sop",
    "biz-profile",
    "biz-tax-team",
    "fsc-corporate-info",
    "g2b-sanctioned-supplier",
    "law-mcp-setup",
    "localdata-business-status",
    "national-pension-workplace",
    "nts-business-registration",
    "nts-tax-delinquency",
    "adaptive-mastery-tutor",
    "cinema-studio-pipeline",
    "cinematic-video-pipeline",
    "min-edit-seedance-2-0",
    "sync-cuts-to-music",
    "timed-storyboard",
    "skill-builder-101",
}
FORBIDDEN_PATTERNS = {
    "raw credential assignment": re.compile(
        r"(?im)^\s*LAW_OC\s*=\s*[\"'][A-Za-z0-9._-]+[\"']\s*$"
    ),
    "skill placeholder": re.compile(r"\[" r"TODO:"),
}
TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yaml", ".yml", ".txt"}
DEPRECATED_MCP_TOOL_NAMES = re.compile(
    r"\b(?:chain_[A-Za-z0-9_]+|analyze_document|get_article_detail|"
    r"search_precedents|summarize_precedent)\b"
)


def main() -> int:
    errors = []
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    mcp_path = ROOT / ".mcp.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"manifest read failed: {exc}", file=sys.stderr)
        return 1

    if manifest.get("name") != ROOT.name:
        errors.append("plugin name must match the repository folder")
    if "korean-law" not in mcp.get("mcpServers", {}):
        errors.append("korean-law MCP entry is missing")

    skills_root = ROOT / "skills"
    installed_skills = {
        path.parent.name
        for path in skills_root.rglob("SKILL.md")
        if not any(
            (parent / "SKILL.md").is_file()
            for parent in path.parent.parents
            if parent != path.parent and parent != skills_root.parent
        )
    }
    missing = REQUIRED_SKILLS - installed_skills
    if missing:
        errors.append(f"missing required skills: {', '.join(sorted(missing))}")

    catalog_path = ROOT / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog_names = {item["name"] for item in catalog["skills"]}
        catalog_docs = {
            item["name"]: item.get("documentation") for item in catalog["skills"]
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"catalog read failed: {exc}")
        catalog_names = set()
        catalog_docs = {}
    if catalog_names != installed_skills:
        missing_from_catalog = sorted(installed_skills - catalog_names)
        extra_in_catalog = sorted(catalog_names - installed_skills)
        if missing_from_catalog:
            errors.append(
                f"catalog missing skills: {', '.join(missing_from_catalog)}"
            )
        if extra_in_catalog:
            errors.append(
                f"catalog has unknown skills: {', '.join(extra_in_catalog)}"
            )

    for skill_name in sorted(installed_skills):
        readme_path = skills_root / skill_name / "README.md"
        if not readme_path.is_file():
            errors.append(f"{skill_name}: missing user-facing README.md")
            continue
        readme = readme_path.read_text(encoding="utf-8", errors="replace")
        if len(readme.strip()) < 1000:
            errors.append(
                f"{skill_name}: README.md is too brief for standalone documentation"
            )
        expected_doc = f"skills/{skill_name}/README.md"
        if catalog_docs.get(skill_name) != expected_doc:
            errors.append(
                f"{skill_name}: catalog documentation must be {expected_doc}"
            )

    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative}: {label}")

    for path in skills_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = DEPRECATED_MCP_TOOL_NAMES.search(text)
        if match:
            errors.append(
                f"{path.relative_to(ROOT)}: deprecated MCP tool name {match.group(0)}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"OK: {len(installed_skills)} skills, Korean Law MCP connector, "
        "and no committed credential assignments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
