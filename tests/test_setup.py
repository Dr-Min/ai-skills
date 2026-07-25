from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPO_ROOT / "scripts" / "setup.py"
SPEC = importlib.util.spec_from_file_location("biz_law_setup", SETUP_PATH)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_discover_skills_in_nested_categories(self) -> None:
        skills = setup.discover_skills(REPO_ROOT / "skills")
        names = {skill.name for skill in skills}

        self.assertIn("biz-legal-team", names)
        self.assertIn("adaptive-mastery-tutor", names)
        self.assertIn("cinematic-video-pipeline", names)
        self.assertIn("skill-builder-101", names)
        self.assertNotIn("zh", names)

    def test_resolve_skills_rejects_unknown_names(self) -> None:
        skills = setup.discover_skills(REPO_ROOT / "skills")

        with self.assertRaisesRegex(setup.SetupError, "찾을 수 없는 스킬"):
            setup.resolve_skills(skills, ["does-not-exist"])

    def test_install_skills_can_install_selected_names_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            backup_dir = Path(temporary) / "backup"

            installed = setup.install_skills(
                REPO_ROOT,
                codex_home,
                backup_dir,
                selected_names=["adaptive-mastery-tutor", "skill-builder-101"],
            )

            self.assertEqual(installed, 2)
            self.assertTrue(
                (codex_home / "skills" / "adaptive-mastery-tutor" / "SKILL.md").is_file()
            )
            self.assertTrue(
                (codex_home / "skills" / "skill-builder-101" / "SKILL.md").is_file()
            )
            self.assertFalse((codex_home / "skills" / "biz-legal-team").exists())

    def test_validate_oc(self) -> None:
        self.assertEqual(setup.validate_oc("sample010103"), "sample010103")
        with self.assertRaises(setup.SetupError):
            setup.validate_oc("bad value")
        with self.assertRaises(setup.SetupError):
            setup.validate_oc("")

    def test_mask_oc(self) -> None:
        self.assertEqual(setup.mask_oc("abc"), "***")
        self.assertEqual(setup.mask_oc("abcdef"), "ab**ef")

    def test_check_node_runtime(self) -> None:
        with mock.patch.object(setup.shutil, "which", return_value=None):
            self.assertFalse(setup.check_node_runtime()[0])

        with (
            mock.patch.object(setup.shutil, "which", side_effect=["node", "npx"]),
            mock.patch.object(setup.subprocess, "check_output", return_value="v20.19.1"),
        ):
            self.assertEqual(setup.check_node_runtime(), (True, "v20.19.1"))

    def test_check_law_api_response_states(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response

        response.read.return_value = b'{"LawSearch":{"resultCode":"00"}}'
        with mock.patch.object(setup.urllib.request, "urlopen", return_value=response):
            self.assertEqual(setup.check_law_api("sample")[0], "connected")

        response.read.return_value = "인증 실패".encode()
        with mock.patch.object(setup.urllib.request, "urlopen", return_value=response):
            self.assertEqual(setup.check_law_api("sample")[0], "rejected")

        response.read.return_value = b"not-json"
        with mock.patch.object(setup.urllib.request, "urlopen", return_value=response):
            self.assertEqual(setup.check_law_api("sample")[0], "unavailable")

        with mock.patch.object(
            setup.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            self.assertEqual(setup.check_law_api("sample")[0], "unavailable")

    def test_resolve_skills_defaults_to_all_and_deduplicates_selection(self) -> None:
        skills = setup.discover_skills(REPO_ROOT / "skills")
        self.assertEqual(setup.resolve_skills(skills), skills)
        selected = setup.resolve_skills(
            skills,
            ["skill-builder-101", "skill-builder-101"],
        )
        self.assertEqual([path.name for path in selected], ["skill-builder-101"])

    def test_main_lists_and_installs_without_law_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root_args = ["--repo-root", str(REPO_ROOT), "--codex-home", temporary]
            with mock.patch("builtins.print") as printer:
                self.assertEqual(setup.main([*root_args, "--list"]), 0)
                self.assertTrue(
                    any(
                        "adaptive-mastery-tutor" in str(call)
                        for call in printer.call_args_list
                    )
                )

            self.assertEqual(
                setup.main(
                    [
                        *root_args,
                        "--no-law-mcp",
                        "--skills",
                        "adaptive-mastery-tutor,skill-builder-101",
                    ]
                ),
                0,
            )
            installed = Path(temporary) / "skills"
            self.assertTrue((installed / "adaptive-mastery-tutor").is_dir())
            self.assertTrue((installed / "skill-builder-101").is_dir())

    def test_main_rejects_unknown_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = setup.main(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "--codex-home",
                    temporary,
                    "--no-law-mcp",
                    "--skills",
                    "unknown-skill",
                ]
            )
        self.assertEqual(result, 1)

    def test_main_runs_law_setup_with_selected_skills(self) -> None:
        result = {
            "masked_oc": "sa****le",
            "node_version": "v20.19.0",
            "connection_status": "skipped",
            "connection_detail": "test",
            "credential_path": "credentials.json",
            "config_backup": "backup.toml",
            "skills_installed": 1,
            "law_mcp_package": setup.LAW_MCP_PACKAGE,
        }
        with mock.patch.object(setup, "run_setup", return_value=result) as runner:
            exit_code = setup.main(
                [
                    "--repo-root",
                    str(REPO_ROOT),
                    "--oc",
                    "sample",
                    "--skills",
                    "law-mcp-setup",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            runner.call_args.kwargs["selected_skill_names"],
            ["law-mcp-setup"],
        )

    def test_remove_mcp_sections_preserves_unrelated_config(self) -> None:
        original = """model = "gpt"

[mcp_servers.alpha]
url = "https://example.com"

[mcp_servers.korean-law]
command = "old"

[mcp_servers.korean-law.env]
DUMMY = "do-not-keep"

[features]
enabled = true
"""
        result = setup.remove_mcp_sections(original)
        self.assertIn("[mcp_servers.alpha]", result)
        self.assertIn("[features]", result)
        self.assertNotIn("mcp_servers.korean-law", result)
        self.assertNotIn("do-not-keep", result)

    def test_run_setup_writes_private_credentials_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text(
                '[mcp_servers.other]\nurl = "https://example.com"\n',
                encoding="utf-8",
            )

            with mock.patch.object(
                setup,
                "check_node_runtime",
                return_value=(True, "v20.19.0"),
            ):
                result = setup.run_setup(
                    repo_root=REPO_ROOT,
                    codex_home=codex_home,
                    oc="sample010103",
                    skip_api_check=True,
                )

            credentials = codex_home / "ai-skills" / "credentials.json"
            self.assertTrue(credentials.is_file())
            payload = json.loads(credentials.read_text(encoding="utf-8"))
            self.assertEqual(payload["LAW_OC"], "sample010103")
            if sys.platform != "win32":
                self.assertEqual(stat.S_IMODE(credentials.stat().st_mode), 0o600)

            updated = config.read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.other]", updated)
            self.assertIn("[mcp_servers.korean-law]", updated)
            self.assertNotIn("sample010103", updated)
            self.assertTrue(Path(result["config_backup"]).is_file())
            self.assertGreaterEqual(result["skills_installed"], 15)


if __name__ == "__main__":
    unittest.main()
