from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPO_ROOT / "scripts" / "setup.py"
SPEC = importlib.util.spec_from_file_location("biz_law_setup", SETUP_PATH)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_validate_oc(self) -> None:
        self.assertEqual(setup.validate_oc("sample010103"), "sample010103")
        with self.assertRaises(setup.SetupError):
            setup.validate_oc("bad value")
        with self.assertRaises(setup.SetupError):
            setup.validate_oc("")

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

            credentials = codex_home / "biz-law-codex" / "credentials.json"
            self.assertTrue(credentials.is_file())
            payload = json.loads(credentials.read_text(encoding="utf-8"))
            self.assertEqual(payload["LAW_OC"], "sample010103")
            self.assertEqual(stat.S_IMODE(credentials.stat().st_mode), 0o600)

            updated = config.read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.other]", updated)
            self.assertIn("[mcp_servers.korean-law]", updated)
            self.assertNotIn("sample010103", updated)
            self.assertTrue(Path(result["config_backup"]).is_file())
            self.assertGreaterEqual(result["skills_installed"], 15)


if __name__ == "__main__":
    unittest.main()
