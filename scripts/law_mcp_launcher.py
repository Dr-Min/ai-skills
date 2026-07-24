#!/usr/bin/env python3
"""Launch korean-law-mcp with a locally stored LAW_OC value."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys


PACKAGE = "korean-law-mcp@4.8.0"
OC_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,128}$")


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _load_oc() -> str:
    from_environment = os.environ.get("LAW_OC", "").strip()
    if from_environment:
        return from_environment

    credential_path = _codex_home() / "biz-law-codex" / "credentials.json"
    try:
        payload = json.loads(credential_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(
            "Law MCP 인증값이 없습니다. Codex에서 'Law MCP 연결해줘'라고 요청하거나 "
            "이 저장소의 `python3 install.py`를 실행하세요."
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Law MCP 인증정보를 읽을 수 없습니다: {exc}") from exc

    return str(payload.get("LAW_OC", "")).strip()


def main() -> int:
    try:
        oc = _load_oc()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not OC_PATTERN.fullmatch(oc):
        print(
            "저장된 LAW_OC 형식이 올바르지 않습니다. 연결 설정을 다시 실행하세요.",
            file=sys.stderr,
        )
        return 2

    npx = shutil.which("npx")
    if not npx:
        print(
            "npx를 찾을 수 없습니다. Node.js 20.19 이상을 설치한 뒤 다시 시도하세요.",
            file=sys.stderr,
        )
        return 127

    environment = os.environ.copy()
    environment["LAW_OC"] = oc
    os.execvpe(npx, [npx, "-y", PACKAGE], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
