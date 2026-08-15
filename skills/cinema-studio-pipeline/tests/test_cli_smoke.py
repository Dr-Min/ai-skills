import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class CliSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.missing = self.root / "missing"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _invoke(self, function, argv: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = function(argv)
        return code, output.getvalue()

    def test_read_only_validator_clis_report_missing_projects(self) -> None:
        from validate_project import main as project_main
        from validate_references import main as references_main
        from verify_lineage import main as lineage_main

        for function, argv in (
            (project_main, [str(self.missing), "--json"]),
            (references_main, [str(self.missing), "--json"]),
            (lineage_main, [str(self.missing), "--json"]),
        ):
            with self.subTest(function=function.__module__):
                code, output = self._invoke(function, argv)
                self.assertNotEqual(0, code)
                self.assertIn("PROJECT_NOT_FOUND", output)

    def test_media_and_export_clis_fail_gracefully_for_missing_inputs(self) -> None:
        from export_timeline import main as export_main
        from extract_review_frames import main as extract_main
        from inspect_media import main as inspect_main
        from make_contact_sheet import main as contact_main

        empty = self.root / "empty"
        empty.mkdir()
        output = self.root / "output.json"
        for function, argv, marker in (
            (export_main, [str(self.missing), str(output)], "TIMELINE_NOT_FOUND"),
            (extract_main, [str(self.missing), str(self.root / "frames")], "MEDIA_NOT_FOUND"),
            (inspect_main, [str(self.missing)], "MEDIA_NOT_FOUND"),
            (contact_main, [str(empty), "--output", str(self.root / "sheet.png")], "NO_IMAGES"),
        ):
            with self.subTest(function=function.__module__):
                code, rendered = self._invoke(function, argv)
                self.assertNotEqual(0, code)
                self.assertIn(marker, rendered)

    def test_install_and_transition_clis_fail_closed(self) -> None:
        from transition_status import main as transition_main
        from validate_install import main as install_main

        install_code, install_output = self._invoke(
            install_main,
            ["--canonical", str(self.missing / "SKILL.md"), "--candidate", str(self.root / "legacy" / "SKILL.md")],
        )
        self.assertNotEqual(0, install_code)
        self.assertIn("CANONICAL_MISSING", install_output)

        transition_code, transition_output = self._invoke(
            transition_main,
            [str(self.missing), "STORY", "DRAFT"],
        )
        self.assertNotEqual(0, transition_code)
        self.assertIn("E_STAGE_PREREQ", transition_output)


if __name__ == "__main__":
    unittest.main()
