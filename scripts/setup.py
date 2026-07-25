#!/usr/bin/env python3
"""Install Biz skills and configure Korean Law MCP for Codex."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Iterable, Optional, Sequence, Tuple
import urllib.error
import urllib.parse
import urllib.request


PLUGIN_NAME = "ai-skills"
LAW_MCP_PACKAGE = "korean-law-mcp@4.8.0"
OC_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,128}$")
MCP_SECTION_PREFIX = "mcp_servers.korean-law"
LAW_API_URL = "https://www.law.go.kr/DRF/lawSearch.do"


class SetupError(RuntimeError):
    """An actionable setup failure."""


def validate_oc(value: str) -> str:
    oc = value.strip()
    if not OC_PATTERN.fullmatch(oc):
        raise SetupError(
            "인증값 형식이 올바르지 않습니다. 영문자·숫자·점·밑줄·하이픈만 "
            "사용한 법제처 OC 값을 입력하세요."
        )
    return oc


def mask_oc(oc: str) -> str:
    if len(oc) <= 4:
        return "*" * len(oc)
    return f"{oc[:2]}{'*' * (len(oc) - 4)}{oc[-2:]}"


def check_node_runtime() -> Tuple[bool, str]:
    node = shutil.which("node")
    npx = shutil.which("npx")
    if not node or not npx:
        return False, "Node.js 또는 npx를 찾을 수 없습니다."

    try:
        output = subprocess.check_output(
            [node, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        ).strip()
        numbers = tuple(int(part) for part in output.lstrip("v").split(".")[:3])
    except (OSError, subprocess.SubprocessError, ValueError):
        return False, "Node.js 버전을 확인할 수 없습니다."

    if numbers < (20, 19, 0):
        return False, f"Node.js 20.19 이상이 필요합니다. 현재 버전: {output}"
    return True, output


def check_law_api(oc: str, timeout: int = 20) -> Tuple[str, str]:
    """Check API connectivity with the supplied OC.

    The public search endpoint can return data for arbitrary non-empty OC values,
    so this confirms request compatibility and connectivity, not ownership or
    issuance of the identifier.
    """
    query = urllib.parse.urlencode(
        {
            "OC": oc,
            "target": "law",
            "type": "JSON",
            "query": "민법",
            "display": "1",
        }
    )
    request = urllib.request.Request(
        f"{LAW_API_URL}?{query}",
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://open.law.go.kr/",
            "User-Agent": "ai-skills/0.2",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "unavailable", f"법제처 API에 연결하지 못했습니다: {exc}"

    lowered = body.lower()
    failure_markers = (
        "사용자 정보 검증 실패",
        "사용자정보 검증 실패",
        "인증 실패",
        "invalid oc",
    )
    if any(marker.lower() in lowered for marker in failure_markers):
        return "rejected", "법제처가 해당 OC 요청을 거부했습니다."

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None

    law_search = payload.get("LawSearch") if isinstance(payload, dict) else None
    if isinstance(law_search, dict) and str(law_search.get("resultCode")) == "00":
        return (
            "connected",
            "법제처 검색 응답을 확인했습니다. OC 발급 여부는 법제처 마이페이지에서 확인하세요.",
        )
    return "unavailable", "법제처가 예상하지 못한 형식으로 응답했습니다."


def remove_mcp_sections(config_text: str) -> str:
    """Remove korean-law tables while preserving every unrelated TOML line."""
    kept = []
    skip = False
    table_pattern = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")

    for line in config_text.splitlines(keepends=True):
        match = table_pattern.match(line.rstrip("\r\n"))
        if match:
            table_name = match.group(1).strip()
            skip = (
                table_name == MCP_SECTION_PREFIX
                or table_name.startswith(f"{MCP_SECTION_PREFIX}.")
            )
        if not skip:
            kept.append(line)

    return "".join(kept).rstrip() + "\n"


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_mcp_block(launcher_path: Path) -> str:
    return (
        "\n[mcp_servers.korean-law]\n"
        'command = "python3"\n'
        f"args = [{toml_string(str(launcher_path))}]\n"
        "startup_timeout_sec = 120\n"
    )


def _write_atomic(path: Path, text: str, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    try:
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def configure_codex(config_path: Path, launcher_path: Path, backup_dir: Path) -> Path:
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "config.toml"
    if config_path.exists():
        shutil.copy2(config_path, backup_path)
    else:
        backup_path.write_text("", encoding="utf-8")

    updated = remove_mcp_sections(existing) + render_mcp_block(launcher_path)
    _write_atomic(config_path, updated)
    return backup_path


def write_credentials(codex_home: Path, oc: str) -> Path:
    credential_path = codex_home / PLUGIN_NAME / "credentials.json"
    payload = json.dumps(
        {"LAW_OC": oc, "source": "open.law.go.kr"},
        ensure_ascii=False,
        indent=2,
    )
    _write_atomic(credential_path, payload + "\n", mode=stat.S_IRUSR | stat.S_IWUSR)
    return credential_path


def copy_runtime(repo_root: Path, codex_home: Path) -> Path:
    runtime_dir = codex_home / PLUGIN_NAME / "scripts"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    launcher_source = repo_root / "scripts" / "law_mcp_launcher.py"
    setup_source = repo_root / "scripts" / "setup.py"
    if not launcher_source.is_file() or not setup_source.is_file():
        raise SetupError("패키지의 실행 스크립트가 누락됐습니다.")
    for source in (launcher_source, setup_source):
        destination = runtime_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
    return runtime_dir / launcher_source.name


def discover_skills(skills_root: Path) -> list[Path]:
    """Find installable skills while allowing category directories.

    A directory containing SKILL.md is one installable unit, so discovery does
    not descend into that directory. This prevents localized files such as
    ``zh/SKILL.md`` from being treated as separate skills.
    """
    if not skills_root.is_dir():
        raise SetupError("패키지의 skills 폴더가 없습니다.")

    discovered: list[Path] = []

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_dir():
                continue
            if (path / "SKILL.md").is_file():
                discovered.append(path)
            else:
                visit(path)

    visit(skills_root)
    return discovered


def resolve_skills(
    available: Sequence[Path],
    selected_names: Optional[Sequence[str]] = None,
) -> list[Path]:
    by_name = {path.name: path for path in available}
    if len(by_name) != len(available):
        raise SetupError("서로 다른 카테고리에 같은 이름의 스킬이 있습니다.")
    if selected_names is None:
        return list(available)

    normalized = [name.strip() for name in selected_names if name.strip()]
    unknown = sorted(set(normalized) - set(by_name))
    if unknown:
        raise SetupError(f"찾을 수 없는 스킬: {', '.join(unknown)}")
    return [by_name[name] for name in dict.fromkeys(normalized)]


def install_skills(
    repo_root: Path,
    codex_home: Path,
    backup_dir: Path,
    selected_names: Optional[Sequence[str]] = None,
) -> int:
    source_root = repo_root / "skills"
    sources = resolve_skills(discover_skills(source_root), selected_names)

    destination_root = codex_home / "skills"
    destination_root.mkdir(parents=True, exist_ok=True)
    count = 0
    for source in sources:
        destination = destination_root / source.name
        if destination.exists():
            skill_backup = backup_dir / "skills" / source.name
            skill_backup.parent.mkdir(parents=True, exist_ok=True)
            if skill_backup.exists():
                shutil.rmtree(skill_backup)
            shutil.copytree(destination, skill_backup)
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        count += 1
    return count


def _repo_root_from_script() -> Path:
    script = Path(__file__).resolve()
    if script.parent.name == "scripts":
        return script.parent.parent
    return script.parent


def run_setup(
    *,
    repo_root: Path,
    codex_home: Path,
    oc: str,
    skip_api_check: bool = False,
    install_skill_files: bool = True,
    selected_skill_names: Optional[Sequence[str]] = None,
) -> dict:
    oc = validate_oc(oc)
    runtime_ok, runtime_detail = check_node_runtime()
    if not runtime_ok:
        raise SetupError(runtime_detail)

    connection_status = "skipped"
    connection_detail = "요청에 따라 API 연결 시험을 건너뛰었습니다."
    if not skip_api_check:
        connection_status, connection_detail = check_law_api(oc)
        if connection_status == "rejected":
            raise SetupError(connection_detail)

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = codex_home / "backups" / f"{PLUGIN_NAME}-{timestamp}"
    launcher_path = copy_runtime(repo_root, codex_home)
    credential_path = write_credentials(codex_home, oc)
    config_backup = configure_codex(
        codex_home / "config.toml",
        launcher_path,
        backup_dir,
    )
    skills_installed = (
        install_skills(
            repo_root,
            codex_home,
            backup_dir,
            selected_names=selected_skill_names,
        )
        if install_skill_files
        else 0
    )

    return {
        "masked_oc": mask_oc(oc),
        "node_version": runtime_detail,
        "connection_status": connection_status,
        "connection_detail": connection_detail,
        "credential_path": str(credential_path),
        "config_backup": str(config_backup),
        "skills_installed": skills_installed,
        "law_mcp_package": LAW_MCP_PACKAGE,
    }


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Biz 스킬을 설치하고 Korean Law MCP를 Codex에 연결합니다."
    )
    parser.add_argument("--oc", help="법제처 Open API OC 인증값")
    parser.add_argument(
        "--codex-home",
        type=Path,
        help="테스트 또는 사용자 지정 Codex 홈 경로",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="패키지 저장소 루트 경로",
    )
    parser.add_argument(
        "--skip-api-check",
        action="store_true",
        help="법제처 API 연결 검증을 건너뜁니다.",
    )
    parser.add_argument(
        "--no-skills",
        action="store_true",
        help="MCP만 설정하고 스킬 파일은 설치하지 않습니다.",
    )
    parser.add_argument(
        "--skills",
        help="설치할 스킬 이름을 쉼표로 구분합니다. 생략하면 전체를 설치합니다.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="설치 가능한 스킬 목록을 출력하고 종료합니다.",
    )
    parser.add_argument(
        "--no-law-mcp",
        action="store_true",
        help="Korean Law MCP 설정 없이 선택한 스킬만 설치합니다.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    codex_home = (
        args.codex_home.expanduser().resolve()
        if args.codex_home
        else Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        .expanduser()
        .resolve()
    )
    repo_root = (
        args.repo_root.expanduser().resolve()
        if args.repo_root
        else _repo_root_from_script()
    )

    available = discover_skills(repo_root / "skills")
    selected_names = (
        [name.strip() for name in args.skills.split(",") if name.strip()]
        if args.skills
        else None
    )

    if args.list:
        try:
            catalog = json.loads(
                (repo_root / "catalog.json").read_text(encoding="utf-8")
            )
            categories = {
                item["name"]: item["category"] for item in catalog["skills"]
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            categories = {}
        for skill in available:
            print(f"{skill.name}\t{categories.get(skill.name, 'uncategorized')}")
        return 0

    try:
        resolve_skills(available, selected_names)
    except SetupError as exc:
        print(f"설치 실패: {exc}", file=sys.stderr)
        return 1

    if args.no_law_mcp:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = codex_home / "backups" / f"{PLUGIN_NAME}-{timestamp}"
        try:
            installed = install_skills(
                repo_root,
                codex_home,
                backup_dir,
                selected_names=selected_names,
            )
        except SetupError as exc:
            print(f"설치 실패: {exc}", file=sys.stderr)
            return 1
        print(f"AI Skills: {installed}개 설치")
        print("Korean Law MCP 설정은 건너뛰었습니다.")
        return 0

    print("AI Skills + Korean Law MCP 설치")
    print("Law MCP 연결을 위해 법제처 Open API 인증값(OC)이 필요합니다.")
    supplied = args.oc
    if supplied is None:
        try:
            supplied = input("당신의 인증 코드는 무엇인가요?\n> ")
        except EOFError:
            print("인증값을 입력받지 못했습니다.", file=sys.stderr)
            return 2

    try:
        result = run_setup(
            repo_root=repo_root,
            codex_home=codex_home,
            oc=supplied,
            skip_api_check=args.skip_api_check,
            install_skill_files=not args.no_skills,
            selected_skill_names=selected_names,
        )
    except SetupError as exc:
        print(f"설치 실패: {exc}", file=sys.stderr)
        return 1

    print(f"인증값: {result['masked_oc']} (로컬에만 저장)")
    print(f"Node.js: {result['node_version']}")
    print(
        "법제처 API 연결 시험: "
        f"{result['connection_status']} — {result['connection_detail']}"
    )
    print(f"Law MCP: {result['law_mcp_package']}")
    print(f"선택한 AI 스킬: {result['skills_installed']}개 설치")
    print(f"기존 설정 백업: {result['config_backup']}")
    print("설치가 끝났습니다. Codex 앱을 다시 시작하거나 새 작업을 여세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
