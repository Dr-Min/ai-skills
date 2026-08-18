import json
import os
import stat
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class CinemaCommonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_safe_project_path_rejects_parent_absolute_and_drive_relative_paths(self) -> None:
        from _cinema_common import safe_project_path

        self.assertEqual(self.root / "04_assets" / "records", safe_project_path(self.root, "04_assets/records"))
        for unsafe in ("../outside.json", str(self.root.anchor) + "outside.json", "C:outside.json"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                safe_project_path(self.root, unsafe)

    def test_asset_index_escape_is_reported_instead_of_read(self) -> None:
        from _cinema_common import discover_asset_paths

        index = self.root / "04_assets" / "asset-index.json"
        index.parent.mkdir(parents=True)
        index.write_text(json.dumps({"records": [{"path": "../outside/asset.json"}]}), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unsafe|escapes"):
            discover_asset_paths(
                self.root,
                {
                    "authority_files": {
                        "asset_records_root": "04_assets/records",
                        "asset_index": "04_assets/asset-index.json",
                    }
                },
            )

    def test_discovery_rejects_symlink_target_outside_project(self) -> None:
        from _cinema_common import discover_shot_paths

        outside = self.root.parent / f"{self.root.name}-outside-shot.json"
        outside.write_text("{}", encoding="utf-8")
        link = self.root / "05_shots" / "S01_SH001" / "shot.json"
        link.parent.mkdir(parents=True)
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            outside.unlink(missing_ok=True)
            self.skipTest(f"symlink creation unavailable: {exc}")
        try:
            with self.assertRaisesRegex(ValueError, "escapes"):
                discover_shot_paths(self.root, {"paths": {"shots": "05_shots"}})
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    def test_shot_discovery_excludes_immutable_history_and_noncanonical_nested_records(self) -> None:
        from _cinema_common import discover_shot_paths

        current = self.root / "05_shots" / "S01_SH001" / "shot.json"
        historical = self.root / "05_shots" / "S01_SH001" / "history" / "v001" / "shot.json"
        unrelated = self.root / "05_shots" / "misc" / "nested" / "shot.json"
        for path in (current, historical, unrelated):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

        self.assertEqual(
            [current.resolve()],
            discover_shot_paths(self.root, {"paths": {"shots": "05_shots"}}),
        )

    def test_take_discovery_accepts_only_the_canonical_current_take_path(self) -> None:
        from _cinema_common import discover_take_paths

        current = (
            self.root
            / "05_shots"
            / "S01_SH001"
            / "takes"
            / "S01_SH001_T01"
            / "take.json"
        )
        historical_mirror = (
            self.root
            / "05_shots"
            / "S01_SH001"
            / "history"
            / "v001"
            / "evidence"
            / "05_shots"
            / "S01_SH001"
            / "takes"
            / "S01_SH001_T01"
            / "take.json"
        )
        unrelated = self.root / "05_shots" / "misc" / "takes" / "not-a-take" / "take.json"
        for path in (current, historical_mirror, unrelated):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

        self.assertEqual(
            [current.resolve()],
            discover_take_paths(self.root, {"paths": {"shots": "05_shots"}}),
        )

    def test_approval_discovery_ignores_template_records(self) -> None:
        from _cinema_common import discover_approval_paths

        template = self.root / "09_approvals" / "_templates" / "APPROVAL.json"
        real = self.root / "09_approvals" / "APR_STORY_0001.json"
        template.parent.mkdir(parents=True)
        template.write_text("{}", encoding="utf-8")
        real.write_text("{}", encoding="utf-8")

        self.assertEqual([real.resolve()], discover_approval_paths(self.root, {"paths": {"approvals": "09_approvals"}}))

    def test_record_id_prefers_authority_identity_over_its_approval_id(self) -> None:
        from _cinema_common import record_id

        authorities = (
            ({"storyboard_id": "board-main", "approval_id": "APR_STORYBOARD_0001"}, "board-main"),
            ({"timeline_id": "edit-main", "approval_id": "APR_EDIT_0001"}, "edit-main"),
            ({"delivery_id": "delivery-main", "approval_id": "APR_FINISH_0001"}, "delivery-main"),
            ({"library_id": "source-main", "approval_id": "APR_SOURCE_LIBRARY_0001"}, "source-main"),
            ({"approval_id": "APR_STORY_0001"}, "APR_STORY_0001"),
        )
        for record, expected in authorities:
            with self.subTest(record=record):
                self.assertEqual(expected, record_id(record))

    def test_central_approval_resolver_binds_exact_current_subject_bytes(self) -> None:
        from _cinema_common import find_bound_approvals, sha256_file

        target = self.root / "02_storyboard" / "storyboard.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"immutable-review-candidate")
        digest = sha256_file(target)
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_STORYBOARD_0001",
            "subject_type": "STORYBOARD",
            "subject_id": "take_me_board",
            "subject_sha256": digest,
            "gate": "STORYBOARD",
            "review_status": "USER_REVIEW_REQUIRED",
            "requested_by": "director",
            "requested_at": "2026-08-12T00:00:00Z",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": target.relative_to(self.root).as_posix(),
                    "sha256": digest,
                    "verified_claim": "exact storyboard review candidate",
                }
            ],
        }
        approval_path = self.root / "09_approvals" / "APR_STORYBOARD_0001.json"
        approvals = [(approval, approval_path)]

        matches = find_bound_approvals(
            self.root,
            approvals,
            project_id="take-me",
            subject_type="STORYBOARD",
            subject_id="take_me_board",
            gate="STORYBOARD",
            target_path=target,
            statuses={"USER_REVIEW_REQUIRED"},
            require_current=True,
        )
        self.assertEqual(approvals, matches)

        approval["superseded_by_approval_id"] = "APR_STORYBOARD_0002"
        self.assertEqual(
            [],
            find_bound_approvals(
                self.root,
                approvals,
                project_id="take-me",
                subject_type="STORYBOARD",
                subject_id="take_me_board",
                gate="STORYBOARD",
                target_path=target,
                statuses={"USER_REVIEW_REQUIRED"},
                require_current=True,
            ),
        )
        self.assertEqual(
            approvals,
            find_bound_approvals(
                self.root,
                approvals,
                project_id="take-me",
                subject_type="STORYBOARD",
                subject_id="take_me_board",
                gate="STORYBOARD",
                target_path=target,
                statuses={"USER_REVIEW_REQUIRED"},
                require_current=False,
            ),
        )

        approval["superseded_by_approval_id"] = None
        target.write_bytes(b"mutated-after-review-request")
        self.assertEqual(
            [],
            find_bound_approvals(
                self.root,
                approvals,
                project_id="take-me",
                subject_type="STORYBOARD",
                subject_id="take_me_board",
                gate="STORYBOARD",
                target_path=target,
                statuses={"USER_REVIEW_REQUIRED"},
                require_current=True,
            ),
        )

    def test_write_json_has_one_winner_without_force_under_concurrency(self) -> None:
        from _cinema_common import read_json, write_json

        target = self.root / "result.json"

        def attempt(index: int) -> str:
            try:
                write_json(target, {"winner": index})
                return "written"
            except FileExistsError:
                return "exists"

        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(attempt, range(16)))

        self.assertEqual(1, outcomes.count("written"), outcomes)
        self.assertEqual(15, outcomes.count("exists"), outcomes)
        self.assertIn(read_json(target)["winner"], range(16))
        self.assertEqual([], list(self.root.glob(".*.tmp")))

    def test_json_writers_reject_nonfinite_numbers_without_publishing(self) -> None:
        from _cinema_common import json_bytes, write_json

        target = self.root / "nonfinite.json"
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    json_bytes({"value": value})
                with self.assertRaises(ValueError):
                    write_json(target, {"value": value})
                self.assertFalse(target.exists())
                self.assertEqual([], list(self.root.glob(".*.tmp")))

    def test_read_json_enforces_the_limit_on_utf8_bytes_not_characters(self) -> None:
        import _cinema_common

        target = self.root / "multibyte.json"
        target.write_text(json.dumps({"value": "한한한"}, ensure_ascii=False), encoding="utf-8")

        with patch.object(_cinema_common, "MAX_JSON_BYTES", 16):
            with self.assertRaisesRegex(json.JSONDecodeError, "safe size limit"):
                _cinema_common.read_json(target)

    def test_name_redirecting_component_detects_direct_and_ancestor_symlinks(self) -> None:
        from _cinema_common import contains_name_redirecting_component

        outside = self.root / "outside"
        outside.mkdir()
        direct = self.root / "direct-link"
        try:
            direct.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        self.assertTrue(contains_name_redirecting_component(direct))
        self.assertTrue(
            contains_name_redirecting_component(direct / "nested" / "output.png")
        )
        self.assertFalse(contains_name_redirecting_component(outside / "regular.png"))

    def test_onedrive_cloud_reparse_tag_is_not_name_redirection(self) -> None:
        from _cinema_common import is_name_redirecting_reparse

        cloud_metadata = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_reparse_tag=0x9000001A,
        )
        with patch("_cinema_common.os.lstat", return_value=cloud_metadata):
            self.assertFalse(is_name_redirecting_reparse(self.root / "cloud"))


if __name__ == "__main__":
    unittest.main()
