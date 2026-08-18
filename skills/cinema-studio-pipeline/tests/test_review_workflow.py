import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.receipt_temporary = tempfile.TemporaryDirectory()
        self.receipt_patcher = patch(
            "decision_receipts.receipt_store_root",
            return_value=Path(self.receipt_temporary.name) / "decision-receipts",
        )
        self.receipt_patcher.start()
        self.project_path = self.root / "project.json"
        self.gates = {
            "STORY": "DRAFT", "STORYBOARD": "DRAFT", "LOOKDEV": "DRAFT",
            "ASSET_LOCK": "DRAFT", "SHOT_STILL": "DRAFT", "RAW_VIDEO": "DRAFT",
            "SOURCE_LIBRARY": "DRAFT", "EDIT": "DRAFT", "FINISH": "DRAFT",
        }
        write_json(self.project_path, {
            "$schema": "00_schemas/project.schema.json",
            "schema_id": "cinema-studio-pipeline/project@2.0.0",
            "schema_version": "2.0.0", "project_id": "review-test", "project_prefix": "REV",
            "title": "Review test", "execution_mode": "GUIDED", "production_mode": "RAW_SOURCE_FIRST",
            "project_status": "ACTIVE", "current_stage": "STORY", "review_status": "DRAFT",
            "stage_gates": self.gates, "approval_policy": {
                "user_approval_after_stills": True, "user_approval_after_video": True,
                "allow_automatic_advance": False,
            },
            "authority_files": {
                "story_contract": "01_story/STORY_CONTRACT.md",
                "storyboard": "02_storyboard/storyboard.json", "visual_bible": "03_lookdev/VISUAL_BIBLE.md",
                "asset_records_root": "04_assets/records", "asset_index": "04_assets/asset-index.json",
                "schema_manifest": "00_schemas/schema-manifest.json",
                "source_manifest": "06_source_library/source_manifest.json",
                "timeline": "07_edit/timeline.json", "delivery_record": "08_delivery/delivery.json",
            },
            "paths": {
                "story": "01_story", "storyboard": "02_storyboard", "lookdev": "03_lookdev",
                "assets": "04_assets", "shots": "05_shots", "source_library": "06_source_library",
                "edit": "07_edit", "delivery": "08_delivery", "approvals": "09_approvals",
                "schemas": "00_schemas", "logs": "99_logs",
            }, "active_approval_ids": [],
        })
        self.story = self.root / "01_story" / "STORY_CONTRACT.md"
        self.story.parent.mkdir(parents=True)
        self.story.write_bytes(b"story authority bytes")
        shutil.copytree(SCRIPTS_DIR.parent / "schemas", self.root / "00_schemas")
        templates = SCRIPTS_DIR.parent / "templates"
        for template_name, relative_target, schema_name in (
            ("STORYBOARD.json", "02_storyboard/storyboard.json", "storyboard"),
            ("SOURCE_MANIFEST.json", "06_source_library/source_manifest.json", "source-library"),
            ("TIMELINE.json", "07_edit/timeline.json", "timeline"),
            ("DELIVERY_RECORD.json", "08_delivery/delivery.json", "delivery"),
        ):
            payload = json.loads((templates / template_name).read_text(encoding="utf-8"))
            payload["project_id"] = "review-test"
            payload["$schema"] = f"../00_schemas/{schema_name}.schema.json"
            write_json(self.root / relative_target, payload)
        visual_bible = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        visual_bible.parent.mkdir(parents=True, exist_ok=True)
        visual_bible.write_bytes((templates / "VISUAL_BIBLE.md").read_bytes())
        asset_records = self.root / "04_assets" / "records"
        asset_records.mkdir(parents=True, exist_ok=True)
        asset_index = json.loads((templates / "ASSET_INDEX.json").read_text(encoding="utf-8"))
        asset_index["project_id"] = "review-test"
        write_json(self.root / "04_assets" / "asset-index.json", asset_index)

    def tearDown(self) -> None:
        self.receipt_patcher.stop()
        self.receipt_temporary.cleanup()
        self.temporary.cleanup()

    def _prepare(self, *, apply: bool) -> dict:
        from prepare_review import prepare_review
        return prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story),
            apply=apply,
        )

    def _prepare_subject(self, subject_type: str, subject_id: str, authority: Path, *, apply: bool = True) -> dict:
        from prepare_review import prepare_review
        return prepare_review(
            self.root, subject_type, subject_id, requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(authority),
            apply=apply,
        )

    def _approve_subject(self, approval_id: str, authority: Path) -> dict:
        from record_decision import record_decision
        approval_path = self.root / "09_approvals" / f"{approval_id}.json"
        return record_decision(
            self.root, approval_id, "approve", actor="project-owner", reference=f"chat-{approval_id}", notes=None,
            expected_project_sha256=sha256(self.project_path), expected_approval_sha256=sha256(approval_path),
            expected_subject_sha256=sha256(authority), apply=True,
        )

    def _write_asset_candidate(self, asset_id: str = "hero") -> tuple[Path, Path]:
        look = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        look.parent.mkdir(parents=True, exist_ok=True)
        look.write_bytes(b"current look authority")
        master = self.root / "04_assets" / "masters" / f"{asset_id}.png"
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(f"master-{asset_id}".encode("utf-8"))
        digest = sha256(master)
        record_path = self.root / "04_assets" / "records" / asset_id / "asset.json"
        write_json(record_path, {
            "$schema": "../../../00_schemas/asset.schema.json",
            "schema_id": "cinema-studio-pipeline/asset@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "asset_id": asset_id, "kind": "CHARACTER",
            "display_name": "Hero", "descriptor": "hero in neutral approved state",
            "state": {
                "label": "base", "isolation": "REQUIRED", "visible_truth": ["neutral front view"],
                "mutually_exclusive_with": [],
            },
            "files": {
                "immutable_master": {"path": master.relative_to(self.root).as_posix(), "sha256": digest},
                "approved_reference": None, "approved_crop": None,
            },
            "lineage": {
                "immutable_master_asset_id": None, "parent_asset_id": None, "derivation": "IMPORTED",
                "source_files": [], "input_hashes": [], "output_sha256": digest,
            },
            "remote": {
                "provider": "Higgsfield", "remote_asset_id": None, "remote_project_id": None,
                "verified": False, "verified_at": None, "evidence": [],
            },
        })
        return record_path, master

    def _write_reviewable_storyboard(
        self,
        panels: list[tuple[str, Path]],
        *,
        storyboard_id: str = "review_board",
    ) -> Path:
        story_approval_path = self.root / "09_approvals" / "APR_STORY_0001.json"
        if not story_approval_path.is_file():
            prepared_story = self._prepare_subject("STORY", "story-contract", self.story)
            self.assertTrue(prepared_story["review_prepared"], prepared_story)
            approved_story = self._approve_subject("APR_STORY_0001", self.story)
            self.assertTrue(approved_story["decision_recorded"], approved_story)

        panel_records = []
        for order, (panel_id, panel_path) in enumerate(panels, start=1):
            panel_records.append({
                "panel_id": panel_id,
                "order": order,
                "duration_hint_seconds": {"minimum": 1, "preferred": 2, "maximum": 3},
                "story_beat": f"Storyboard beat {order}",
                "action": {
                    "start_state": "start",
                    "end_state": "end",
                    "path": {"type": "SCREEN_DIRECTION", "description": "left to right", "waypoints": []},
                },
                "camera": {"shot_size": "MEDIUM", "angle": "EYE_LEVEL", "movement": "LOCKED"},
                "image_file": panel_path.relative_to(self.root).as_posix(),
                "image_sha256": sha256(panel_path),
                "active_assets": [],
            })
        board = self.root / "02_storyboard" / "storyboard.json"
        write_json(board, {
            "$schema": "../00_schemas/storyboard.schema.json",
            "schema_id": "cinema-studio-pipeline/storyboard@2.0.0",
            "schema_version": "2.0.0",
            "project_id": "review-test",
            "storyboard_id": storyboard_id,
            "version": 1,
            "rough_level": 1,
            "story_dependency": {
                "path": self.story.relative_to(self.root).as_posix(),
                "sha256": sha256(self.story),
                "approval_id": "APR_STORY_0001",
            },
            "asset_plan": [
                {"asset_id": "planned_hero", "kind": "CHARACTER", "state_label": "base", "purpose": "Planned screen subject"}
            ],
            "scenes": [{"scene_id": "S01", "order": 1, "panels": panel_records}],
            "shot_plan": [{
                "shot_id": "S01_SH001",
                "scene_id": "S01",
                "order": 1,
                "storyboard_panel_ids": [item["panel_id"] for item in panel_records],
                "required_asset_ids": [],
                "coverage_requirements": [{
                    "coverage_id": "COV_MAIN",
                    "kind": "MASTER",
                    "description": "Primary scene coverage",
                    "minimum_approved_takes": 1,
                }],
            }],
        })
        return board

    def _write_shot_candidate(self) -> tuple[Path, Path]:
        story_approval_id = "APR_STORY_0001"
        prepared_story = self._prepare_subject("STORY", "story-contract", self.story)
        self.assertTrue(prepared_story["review_prepared"], prepared_story)
        approved_story = self._approve_subject(story_approval_id, self.story)
        self.assertTrue(approved_story["decision_recorded"], approved_story)
        story_approval = self.root / "09_approvals" / f"{story_approval_id}.json"

        panel = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        panel.parent.mkdir(parents=True, exist_ok=True)
        panel.write_bytes(b"approved storyboard panel")
        board = self.root / "02_storyboard" / "storyboard.json"
        write_json(board, {
            "$schema": "../00_schemas/storyboard.schema.json",
            "schema_id": "cinema-studio-pipeline/storyboard@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "storyboard_id": "review_board", "version": 1, "rough_level": 1,
            "story_dependency": {
                "path": self.story.relative_to(self.root).as_posix(), "sha256": sha256(self.story),
                "approval_id": story_approval_id,
            },
            "asset_plan": [],
            "scenes": [{
                "scene_id": "S01", "order": 1,
                "panels": [{
                    "panel_id": "S01_P001", "order": 1,
                    "duration_hint_seconds": {"minimum": 1, "preferred": 2, "maximum": 3},
                    "story_beat": "The subject crosses frame",
                    "action": {
                        "start_state": "left", "end_state": "right",
                        "path": {"type": "SCREEN_DIRECTION", "description": "left to right", "waypoints": []},
                    },
                    "camera": {"shot_size": "MEDIUM", "angle": "EYE_LEVEL", "movement": "LOCKED"},
                    "image_file": panel.relative_to(self.root).as_posix(), "image_sha256": sha256(panel),
                    "active_assets": [],
                }],
            }],
            "shot_plan": [{
                "shot_id": "S01_SH001", "scene_id": "S01", "order": 1,
                "storyboard_panel_ids": ["S01_P001"], "required_asset_ids": [],
                "coverage_requirements": [{
                    "coverage_id": "COV_MAIN", "kind": "MASTER", "description": "Primary motion coverage",
                    "minimum_approved_takes": 1,
                }],
            }],
        })
        board_approval_id = "APR_STORYBOARD_0001"
        prepared_board = self._prepare_subject("STORYBOARD", "review_board", board)
        self.assertTrue(prepared_board["review_prepared"], prepared_board)
        approved_board = self._approve_subject(board_approval_id, board)
        self.assertTrue(approved_board["decision_recorded"], approved_board)
        board_approval = self.root / "09_approvals" / f"{board_approval_id}.json"

        look = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        look.parent.mkdir(parents=True, exist_ok=True)
        look.write_bytes(b"approved look authority")
        look_approval_id = "APR_LOOKDEV_0001"
        prepared_look = self._prepare_subject("LOOKDEV", "visual-bible", look)
        self.assertTrue(prepared_look["review_prepared"], prepared_look)
        approved_look = self._approve_subject(look_approval_id, look)
        self.assertTrue(approved_look["decision_recorded"], approved_look)
        look_approval = self.root / "09_approvals" / f"{look_approval_id}.json"

        still = self.root / "05_shots" / "S01_SH001" / "still.png"
        still.parent.mkdir(parents=True, exist_ok=True)
        still.write_bytes(b"approved still pixels")

        def binding(subject_type: str, subject_id: str, approval_id: str, authority: Path, approval_path: Path) -> dict:
            return {
                "subject_type": subject_type, "subject_id": subject_id, "approval_id": approval_id,
                "review_status": "USER_APPROVED", "subject_sha256": sha256(authority),
                "authority_path": authority.relative_to(self.root).as_posix(),
                "approval_record_path": approval_path.relative_to(self.root).as_posix(),
            }

        shot = still.parent / "shot.json"
        shot_payload = json.loads((SCRIPTS_DIR.parent / "templates" / "SHOT_CARD.json").read_text(encoding="utf-8"))
        shot_payload.update({
            "$schema": "../../00_schemas/shot.schema.json",
            "project_id": "review-test", "shot_id": "S01_SH001", "scene_id": "S01",
            "storyboard_panel_ids": ["S01_P001"], "coverage_requirement_ids": ["COV_MAIN"],
            "still_evidence": [{
                "role": "STILL", "asset_id": None,
                "path": still.relative_to(self.root).as_posix(), "sha256": sha256(still),
            }],
            "dependency_snapshot": {
                "project_id": "review-test", "captured_at": "2026-08-12T00:00:00Z",
                "story": binding("STORY", "story-contract", story_approval_id, self.story, story_approval),
                "storyboard": binding("STORYBOARD", "review_board", board_approval_id, board, board_approval),
                "lookdev": binding("LOOKDEV", "visual-bible", look_approval_id, look, look_approval),
                "required_assets": [],
            },
        })
        write_json(shot, shot_payload)
        return shot, still

    def _write_take_candidate(self, take_id: str = "S01_SH001_T01") -> tuple[Path, Path]:
        shot, _ = self._write_shot_candidate()
        prepared_shot = self._prepare_subject("SHOT_STILL", "S01_SH001", shot)
        self.assertTrue(prepared_shot["review_prepared"], prepared_shot)
        approved_shot = self._approve_subject("APR_SHOT_STILL_0001", shot)
        self.assertTrue(approved_shot["decision_recorded"], approved_shot)

        output = self.root / "05_shots" / "S01_SH001" / "takes" / take_id / "out.mov"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"reviewable take output")
        remote_package = self.root / "99_logs" / "remote" / "job-1.json"
        write_json(remote_package, {
            "verification_scope": "OFFLINE_RECORD_CONSISTENCY", "provider": "Higgsfield",
            "project_id": "remote-project-1", "job_id": "job-1", "model_name": "Seedance",
            "output_sha256": sha256(output),
        })
        record_path = output.parent / "take.json"
        write_json(record_path, {
            "$schema": "../../../../00_schemas/take.schema.json",
            "schema_id": "cinema-studio-pipeline/take@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "take_id": take_id, "shot_id": "S01_SH001",
            "output_file": output.relative_to(self.root).as_posix(),
            "output_sha256": sha256(output), "coverage_requirement_ids": ["COV_MAIN"],
            "input_hashes": [
                {"path": shot.relative_to(self.root).as_posix(), "sha256": sha256(shot)},
                {"path": remote_package.relative_to(self.root).as_posix(), "sha256": sha256(remote_package)},
            ],
            "prompt_version": 1,
            "execution_origin": "REMOTE_GENERATION", "remote_job_id": "job-1",
            "remote_url": None,
            "remote": {
                "provider": "Higgsfield", "project_id": "remote-project-1", "job_id": "job-1",
                "verified": True, "verified_at": "2026-08-12T00:00:00Z",
                "evidence": [{
                    "path": remote_package.relative_to(self.root).as_posix(), "sha256": sha256(remote_package),
                    "verified_claim": "Offline remote job record consistency",
                }],
            },
            "model": {
                "provider": "Higgsfield", "name": "Seedance", "version": "2.0", "verified": True,
                "verified_at": "2026-08-12T00:00:00Z",
            },
            "generation_parameters": {"duration_seconds": 1},
            "diagnosis": {
                "verdict": "PASS", "first_failure": None, "at_seconds": None,
                "what_held": ["continuity"], "changed_variable": None, "next_action": None,
            },
            "lineage": {"parent_take_id": None, "source_take_ids": [], "source_asset_ids": [], "derivation": "GENERATED"},
        })
        return record_path, output

    def test_asset_prepare_publishes_exact_media_and_record_evidence(self) -> None:
        record_path, master = self._write_asset_candidate()
        result = self._prepare_subject("ASSET", "hero", master)

        self.assertTrue(result["review_prepared"], result)
        approval_path = self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        pairs = {(item["path"], item["sha256"]) for item in approval["evidence"]}
        self.assertIn((master.relative_to(self.root).as_posix(), sha256(master)), pairs)
        self.assertIn((record_path.relative_to(self.root).as_posix(), sha256(record_path)), pairs)

    def test_asset_approve_records_the_explicit_user_decision(self) -> None:
        _, master = self._write_asset_candidate()
        prepared = self._prepare_subject("ASSET", "hero", master)
        self.assertTrue(prepared["review_prepared"], prepared)

        result = self._approve_subject("APR_ASSET_LOCK_0001", master)

        self.assertTrue(result["decision_recorded"], result)
        approval = json.loads(
            (self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json").read_text(encoding="utf-8")
        )
        self.assertEqual("USER_APPROVED", approval["review_status"])
        self.assertEqual("USER", approval["decided_by_type"])
        self.assertEqual("chat-APR_ASSET_LOCK_0001", approval["user_evidence_reference"])

    def test_take_prepare_publishes_exact_output_and_record_evidence(self) -> None:
        record_path, output = self._write_take_candidate()
        result = self._prepare_subject("TAKE", "S01_SH001_T01", output)

        self.assertTrue(result["review_prepared"], result)
        approval_path = self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        pairs = {(item["path"], item["sha256"]) for item in approval["evidence"]}
        self.assertIn((output.relative_to(self.root).as_posix(), sha256(output)), pairs)
        self.assertIn((record_path.relative_to(self.root).as_posix(), sha256(record_path)), pairs)

    def test_take_approve_records_the_explicit_user_decision(self) -> None:
        _, output = self._write_take_candidate()
        prepared = self._prepare_subject("TAKE", "S01_SH001_T01", output)
        self.assertTrue(prepared["review_prepared"], prepared)

        result = self._approve_subject("APR_RAW_VIDEO_0001", output)

        self.assertTrue(result["decision_recorded"], result)
        approval = json.loads(
            (self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json").read_text(encoding="utf-8")
        )
        self.assertEqual("USER_APPROVED", approval["review_status"])
        self.assertEqual("USER", approval["decided_by_type"])
        self.assertEqual("chat-APR_RAW_VIDEO_0001", approval["user_evidence_reference"])

    def test_asset_decision_rejects_stale_asset_record_evidence_without_publishing(self) -> None:
        record_path, master = self._write_asset_candidate()
        prepared = self._prepare_subject("ASSET", "hero", master)
        self.assertTrue(prepared["review_prepared"], prepared)
        approval_path = self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json"
        approval_before = approval_path.read_bytes()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["descriptor"] = "mutated after review preparation"
        write_json(record_path, record)

        result = self._approve_subject("APR_ASSET_LOCK_0001", master)

        self.assertFalse(result["allowed"], result)
        self.assertFalse(result["decision_recorded"], result)
        self.assertEqual(approval_before, approval_path.read_bytes())

    def test_take_decision_rejects_stale_take_record_evidence_without_publishing(self) -> None:
        record_path, output = self._write_take_candidate()
        prepared = self._prepare_subject("TAKE", "S01_SH001_T01", output)
        self.assertTrue(prepared["review_prepared"], prepared)
        approval_path = self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        approval_before = approval_path.read_bytes()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["generation_parameters"]["duration_seconds"] = 2
        write_json(record_path, record)

        result = self._approve_subject("APR_RAW_VIDEO_0001", output)

        self.assertFalse(result["allowed"], result)
        self.assertFalse(result["decision_recorded"], result)
        self.assertEqual(approval_before, approval_path.read_bytes())

    def test_asset_decision_rejects_changed_master_even_with_current_caller_hash(self) -> None:
        _, master = self._write_asset_candidate()
        prepared = self._prepare_subject("ASSET", "hero", master)
        self.assertTrue(prepared["review_prepared"], prepared)
        approval_path = self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json"
        approval_before = approval_path.read_bytes()
        master.write_bytes(b"different master bytes after review preparation")

        result = self._approve_subject("APR_ASSET_LOCK_0001", master)

        self.assertFalse(result["allowed"], result)
        self.assertFalse(result["decision_recorded"], result)
        self.assertEqual(approval_before, approval_path.read_bytes())

    def test_take_decision_rejects_changed_output_even_with_current_caller_hash(self) -> None:
        _, output = self._write_take_candidate()
        prepared = self._prepare_subject("TAKE", "S01_SH001_T01", output)
        self.assertTrue(prepared["review_prepared"], prepared)
        approval_path = self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        approval_before = approval_path.read_bytes()
        output.write_bytes(b"different take bytes after review preparation")

        result = self._approve_subject("APR_RAW_VIDEO_0001", output)

        self.assertFalse(result["allowed"], result)
        self.assertFalse(result["decision_recorded"], result)
        self.assertEqual(approval_before, approval_path.read_bytes())

    def test_take_decision_preserves_the_exact_prepared_record_and_media_evidence(self) -> None:
        record_path, output = self._write_take_candidate()
        prepared = self._prepare_subject("TAKE", "S01_SH001_T01", output)
        self.assertTrue(prepared["review_prepared"], prepared)
        approval_path = self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        pending = json.loads(approval_path.read_text(encoding="utf-8"))
        prepared_evidence = pending["evidence"]
        record_bytes = record_path.read_bytes()
        output_bytes = output.read_bytes()

        result = self._approve_subject("APR_RAW_VIDEO_0001", output)

        self.assertTrue(result["decision_recorded"], result)
        decided = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual(prepared_evidence, decided["evidence"])
        self.assertEqual(record_bytes, record_path.read_bytes())
        self.assertEqual(output_bytes, output.read_bytes())

    def test_review_candidate_rejects_preexisting_invalid_authority_semantics(self) -> None:
        from validate_project import validate_review_candidate

        record_path, master = self._write_asset_candidate()
        board = self.root / "02_storyboard" / "storyboard.json"
        write_json(board, {
            "$schema": "../00_schemas/storyboard.schema.json",
            "schema_id": "cinema-studio-pipeline/storyboard@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "storyboard_id": "invalid_board", "version": 1, "rough_level": 1,
            "story_dependency": None, "asset_plan": [],
            "scenes": [
                {"scene_id": "S01", "order": 1, "scene_purpose": "first", "panels": []},
                {"scene_id": "S01", "order": 1, "scene_purpose": "duplicate", "panels": []},
            ],
            "shot_plan": [],
        })
        look = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        approval = {
            "$schema": "../00_schemas/approval.schema.json",
            "schema_id": "cinema-studio-pipeline/approval@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "approval_id": "APR_ASSET_LOCK_0001",
            "subject_type": "ASSET", "subject_id": "hero", "subject_sha256": sha256(master),
            "gate": "ASSET_LOCK", "review_status": "USER_REVIEW_REQUIRED",
            "requested_by": "director", "requested_at": "2026-08-12T00:00:00Z",
            "evidence": [
                {"path": master.relative_to(self.root).as_posix(), "sha256": sha256(master), "verified_claim": "Current content authority"},
                {"path": record_path.relative_to(self.root).as_posix(), "sha256": sha256(record_path), "verified_claim": "Asset authority record"},
                {"path": look.relative_to(self.root).as_posix(), "sha256": sha256(look), "verified_claim": "Current lookdev authority"},
            ],
            "supersedes_approval_id": None, "superseded_by_approval_id": None,
        }

        result = validate_review_candidate(self.root, "ASSET", "hero", approval)

        self.assertFalse(result["ok"], result)
        self.assertTrue(any(item["code"] == "DUPLICATE_ID" for item in result["errors"]), result)

    def test_prepare_rejects_preexisting_invalid_authority_semantics_before_publication(self) -> None:
        _, master = self._write_asset_candidate()
        board = self.root / "02_storyboard" / "storyboard.json"
        write_json(board, {
            "$schema": "../00_schemas/storyboard.schema.json",
            "schema_id": "cinema-studio-pipeline/storyboard@2.0.0", "schema_version": "2.0.0",
            "project_id": "review-test", "storyboard_id": "invalid_board", "version": 1, "rough_level": 1,
            "story_dependency": None, "asset_plan": [],
            "scenes": [
                {"scene_id": "S01", "order": 1, "scene_purpose": "first", "panels": []},
                {"scene_id": "S01", "order": 1, "scene_purpose": "duplicate", "panels": []},
            ],
            "shot_plan": [],
        })

        result = self._prepare_subject("ASSET", "hero", master)

        self.assertFalse(result["allowed"], result)
        self.assertFalse(result["review_prepared"], result)
        self.assertFalse((self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json").exists())

    def test_prepare_is_dry_run_until_apply_creates_immutable_snapshot_and_central_request(self) -> None:
        dry_run = self._prepare(apply=False)
        approval_path = self.root / "09_approvals" / "APR_STORY_0001.json"
        archive = self.root / "01_story" / "history" / "story-contract" / "v001" / "STORY_CONTRACT.md"
        self.assertTrue(dry_run["allowed"], dry_run)
        self.assertFalse(dry_run["review_prepared"])
        self.assertFalse(approval_path.exists())
        self.assertFalse(archive.exists())

        result = self._prepare(apply=True)
        self.assertTrue(result["review_prepared"], result)
        self.assertTrue(result["gate_activated"], result)
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual("../00_schemas/approval.schema.json", approval["$schema"])
        self.assertEqual("USER_REVIEW_REQUIRED", approval["review_status"])
        self.assertEqual(sha256(self.story), approval["subject_sha256"])
        self.assertEqual(self.story.read_bytes(), archive.read_bytes())
        pairs = {(item["path"], item["sha256"]) for item in approval["evidence"]}
        self.assertIn(("01_story/STORY_CONTRACT.md", sha256(self.story)), pairs)
        self.assertIn(("01_story/history/story-contract/v001/STORY_CONTRACT.md", sha256(self.story)), pairs)

    def test_prepare_fails_closed_when_subject_or_project_cas_is_stale(self) -> None:
        from prepare_review import prepare_review
        stale_subject = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256="0" * 64, apply=True,
        )
        self.assertFalse(stale_subject["allowed"])
        self.assertFalse((self.root / "09_approvals").exists())
        stale_project = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256="0" * 64, expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertFalse(stale_project["allowed"])
        self.assertFalse((self.root / "09_approvals").exists())

    def test_prepare_removes_only_its_new_archive_when_approval_publication_fails(self) -> None:
        archive_root = self.root / "01_story" / "history" / "story-contract" / "v001"
        with patch("prepare_review._atomic_create_json", side_effect=OSError("forced publication failure")):
            failed = self._prepare(apply=True)

        self.assertFalse(failed["allowed"], failed)
        self.assertFalse((self.root / "09_approvals" / "APR_STORY_0001.json").exists())
        self.assertFalse(archive_root.exists(), "failed publication must not strand an orphan review version")

        retried = self._prepare(apply=True)
        self.assertTrue(retried["review_prepared"], retried)
        self.assertEqual("v001", retried["archive_version"])
        self.assertTrue((archive_root / "STORY_CONTRACT.md").is_file())

    def test_prepare_requires_the_trusted_project_schema_snapshot_and_rejects_duplicate_pending_subject(self) -> None:
        from prepare_review import prepare_review
        (self.root / "00_schemas" / "approval.schema.json").unlink()
        missing_schema = self._prepare(apply=False)
        self.assertFalse(missing_schema["allowed"], missing_schema)
        shutil.copy2(SCRIPTS_DIR.parent / "schemas" / "approval.schema.json", self.root / "00_schemas" / "approval.schema.json")
        self.assertTrue(self._prepare(apply=True)["review_prepared"])
        duplicate = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story), apply=False,
        )
        self.assertFalse(duplicate["allowed"], duplicate)

    def test_prepare_requires_a_new_asset_id_after_any_terminal_decision(self) -> None:
        from prepare_review import prepare_review

        _, master = self._write_asset_candidate("hero")
        first = self._prepare_subject("ASSET", "hero", master)
        self.assertTrue(first["review_prepared"], first)
        approval_path = self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval.update(
            {
                "review_status": "EXCLUDED_FROM_INPUTS",
                "decided_by_type": "USER",
                "decided_by": "project-owner",
                "decided_at": "2026-08-12T01:00:00Z",
                "decision_notes": "Create a replacement under a new asset ID.",
            }
        )
        approval_path.write_text(json.dumps(approval, indent=2), encoding="utf-8")

        duplicate = prepare_review(
            self.root,
            "ASSET",
            "hero",
            requested_by="director",
            expected_project_sha256=sha256(self.project_path),
            expected_subject_sha256=sha256(master),
            apply=False,
        )

        self.assertFalse(duplicate["allowed"], duplicate)
        self.assertIn(
            "E_REVISION_WORKFLOW_UNSUPPORTED",
            {item["code"] for item in duplicate["errors"]},
        )

    def test_record_approve_is_cas_guarded_and_advances_the_prepared_story_gate(self) -> None:
        self._prepare(apply=True)
        from record_decision import record_decision
        approval_path = self.root / "09_approvals" / "APR_STORY_0001.json"
        before = sha256(approval_path)
        mismatch = record_decision(
            self.root, "APR_STORY_0001", "approve", actor="project-owner", reference="chat-42",
            notes="looks good", expected_project_sha256=sha256(self.project_path),
            expected_approval_sha256="0" * 64, expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertFalse(mismatch["allowed"])
        self.assertEqual(before, sha256(approval_path))

        result = record_decision(
            self.root, "APR_STORY_0001", "approve", actor="project-owner", reference="chat-42",
            notes="looks good", expected_project_sha256=sha256(self.project_path),
            expected_approval_sha256=before, expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertTrue(result["decision_recorded"], result)
        self.assertTrue(result["gate_activated"], result)
        decision = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual("USER_APPROVED", decision["review_status"])
        self.assertEqual("USER", decision["decided_by_type"])
        self.assertEqual("chat-42", decision["user_evidence_reference"])
        project = json.loads(self.project_path.read_text(encoding="utf-8"))
        self.assertEqual("USER_APPROVED", project["stage_gates"]["STORY"])
        self.assertEqual("STORYBOARD", project["current_stage"])

    def test_forged_terminal_approval_without_machine_receipt_is_rejected(self) -> None:
        from validate_project import validate_project

        receipt_store = self.root.parent / f"{self.root.name}-receipts"
        with patch("decision_receipts.receipt_store_root", return_value=receipt_store):
            prepared = self._prepare(apply=True)
            self.assertTrue(prepared["gate_activated"], prepared)
            approval_path = self.root / "09_approvals" / "APR_STORY_0001.json"
            forged = json.loads(approval_path.read_text(encoding="utf-8"))
            forged.update(
                {
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "decided_by": "forger",
                    "decided_at": "2026-08-12T01:00:00Z",
                    "user_evidence_reference": "forged-json",
                }
            )
            approval_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")

            validation = validate_project(self.root)

        self.assertFalse(validation["ok"], validation)
        self.assertIn(
            "DECISION_RECEIPT_INVALID",
            {item["code"] for item in validation["errors"]},
        )

    def test_reject_syncs_a_singleton_gate(self) -> None:
        from record_decision import record_decision
        self._prepare(apply=True)
        story_approval = self.root / "09_approvals" / "APR_STORY_0001.json"
        pending_hash = sha256(story_approval)
        missing_notes = record_decision(
            self.root, "APR_STORY_0001", "reject", actor="project-owner", reference=None, notes=None,
            expected_project_sha256=sha256(self.project_path), expected_approval_sha256=pending_hash,
            expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertFalse(missing_notes["allowed"], missing_notes)
        self.assertEqual(pending_hash, sha256(story_approval))

        rejected = record_decision(
            self.root, "APR_STORY_0001", "reject", actor="project-owner", reference=None, notes="needs work",
            expected_project_sha256=sha256(self.project_path), expected_approval_sha256=pending_hash,
            expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertTrue(rejected["decision_recorded"], rejected)
        self.assertTrue(rejected["gate_activated"], rejected)
        decision = json.loads(story_approval.read_text(encoding="utf-8"))
        self.assertEqual("REJECTED", decision["review_status"])
        self.assertEqual("needs work", decision["decision_notes"])
        self.assertIsNone(decision.get("user_evidence_reference"))
        project = json.loads(self.project_path.read_text(encoding="utf-8"))
        self.assertEqual("REJECTED", project["stage_gates"]["STORY"])

    def test_reject_never_closes_a_collection_gate(self) -> None:
        from record_decision import record_decision

        _, output = self._write_take_candidate()
        prepared = self._prepare_subject("TAKE", "S01_SH001_T01", output)
        self.assertTrue(prepared["review_prepared"], prepared)
        take_approval = self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        with patch("transition_status.apply_transition") as transition:
            rejected_collection = record_decision(
                self.root, "APR_RAW_VIDEO_0001", "reject", actor="project-owner", reference=None, notes="rerender",
                expected_project_sha256=sha256(self.project_path), expected_approval_sha256=sha256(take_approval),
                expected_subject_sha256=sha256(output), apply=True,
            )
        self.assertTrue(rejected_collection["decision_recorded"], rejected_collection)
        self.assertFalse(rejected_collection["gate_activated"], rejected_collection)
        transition.assert_not_called()

    def test_record_decision_rejects_an_aliased_central_approval_target_before_writing(self) -> None:
        self._prepare(apply=True)
        from record_decision import record_decision
        approval = self.root / "09_approvals" / "APR_STORY_0001.json"
        before = sha256(approval)
        with patch("record_decision._assert_safe_write_target", side_effect=ValueError("approval target alias")):
            result = record_decision(
                self.root, "APR_STORY_0001", "approve", actor="owner", reference="chat-1", notes=None,
                expected_project_sha256=sha256(self.project_path), expected_approval_sha256=before,
                expected_subject_sha256=sha256(self.story), apply=True,
            )
        self.assertFalse(result["allowed"], result)
        self.assertEqual(before, sha256(approval))

    def test_prepare_fails_closed_on_scalar_central_approval_record(self) -> None:
        malformed = self.root / "09_approvals" / "malformed.json"
        malformed.parent.mkdir(parents=True, exist_ok=True)
        malformed.write_text("[]", encoding="utf-8")

        result = self._prepare(apply=False)

        self.assertFalse(result["allowed"], result)
        self.assertIn("object", result["errors"][0]["message"].casefold())

    def test_review_public_boundaries_reject_invalid_utf8_project_without_traceback(self) -> None:
        from record_decision import record_decision

        self.project_path.write_bytes(b"\xff\xfeinvalid")
        prepared = self._prepare(apply=False)
        decided = record_decision(
            self.root,
            "APR_STORY_0001",
            "approve",
            actor="director",
            reference="chat",
            notes=None,
            expected_project_sha256=sha256(self.project_path),
            expected_approval_sha256="0" * 64,
            expected_subject_sha256=sha256(self.story),
            apply=False,
        )

        self.assertFalse(prepared["allowed"], prepared)
        self.assertFalse(decided["allowed"], decided)

    def test_timeline_requires_an_existing_current_immutable_candidate(self) -> None:
        from prepare_review import prepare_review
        result = prepare_review(
            self.root, "TIMELINE", "picture-lock", requested_by="editor",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256="0" * 64, apply=False,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any(item["code"] == "E_APPROVAL_HASH_MISMATCH" for item in result["errors"]), result)

    def test_source_library_review_copies_admitted_source_evidence_to_the_exact_archive(self) -> None:
        from prepare_review import prepare_review
        _, admitted = self._write_take_candidate()
        prepared_take = self._prepare_subject("TAKE", "S01_SH001_T01", admitted)
        self.assertTrue(prepared_take["review_prepared"], prepared_take)
        approved_take = self._approve_subject("APR_RAW_VIDEO_0001", admitted)
        self.assertTrue(approved_take["decision_recorded"], approved_take)

        source = self.root / "06_source_library" / "source_manifest.json"
        write_json(source, {
            "$schema": "../00_schemas/source-library.schema.json",
            "schema_id": "cinema-studio-pipeline/source-library@2.0.0",
            "schema_version": "2.0.0",
            "project_id": "review-test", "library_id": "source_library",
            "lock_status": "SOURCE_LOCKED", "sources": [{
                "source_id": "SRC_S01_SH001_T01", "take_id": "S01_SH001_T01",
                "path": "05_shots/S01_SH001/takes/S01_SH001_T01/out.mov", "sha256": sha256(admitted),
                "source_status": "SOURCE_APPROVED",
            }],
        })
        source_result = prepare_review(
            self.root, "SOURCE_LIBRARY", "source_library", requested_by="editor",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(source), apply=True,
        )
        self.assertTrue(source_result["review_prepared"], source_result)
        self.assertTrue((self.root / "06_source_library" / "history" / "source_library" / "v001" / "source_manifest.json").is_file())
        self.assertEqual(admitted.read_bytes(), (self.root / "06_source_library" / "history" / "source_library" / "v001" / "evidence" / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "out.mov").read_bytes())

    def test_shot_review_copies_required_pixel_evidence_to_the_exact_archive(self) -> None:
        shot, still = self._write_shot_candidate()
        shot_result = self._prepare_subject("SHOT_STILL", "S01_SH001", shot)
        self.assertTrue(shot_result["review_prepared"], shot_result)
        archive = self.root / "05_shots" / "S01_SH001" / "history" / "v001"
        self.assertEqual(shot.read_bytes(), (archive / "shot.json").read_bytes())
        self.assertEqual(still.read_bytes(), (archive / "evidence" / "05_shots" / "S01_SH001" / "still.png").read_bytes())

    def test_storyboard_nested_scene_panels_are_deduplicated_and_archived_as_pixel_evidence(self) -> None:
        from prepare_review import prepare_review
        panel = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        panel.parent.mkdir(parents=True)
        panel.write_bytes(b"nested-panel-pixels")
        storyboard = self._write_reviewable_storyboard(
            [("S01_P001", panel), ("S01_P002", panel)]
        )
        result = prepare_review(
            self.root, "STORYBOARD", "review_board", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(storyboard), apply=True,
        )
        self.assertTrue(result["review_prepared"], result)
        approval = json.loads((self.root / "09_approvals" / "APR_STORYBOARD_0001.json").read_text(encoding="utf-8"))
        panel_pairs = [item for item in approval["evidence"] if item["path"].endswith("S01_P001.png")]
        self.assertEqual(2, len(panel_pairs), panel_pairs)  # current + immutable mirror
        story_pairs = [item for item in approval["evidence"] if item["path"].endswith("STORY_CONTRACT.md")]
        self.assertEqual(2, len(story_pairs), story_pairs)  # dependency + immutable mirror
        self.assertTrue((self.root / "02_storyboard" / "history" / "review_board" / "v001" / "evidence" / "02_storyboard" / "panels" / "S01_P001.png").is_file())

    def test_lookdev_includes_current_storyboard_and_nested_panel_evidence(self) -> None:
        from prepare_review import prepare_review
        panel = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        panel.parent.mkdir(parents=True)
        panel.write_bytes(b"board pixels")
        board = self._write_reviewable_storyboard([("S01_P001", panel)])
        look = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        look.parent.mkdir(exist_ok=True)
        look.write_bytes(b"look authority")
        result = prepare_review(
            self.root, "LOOKDEV", "visual-bible", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(look), apply=True,
        )
        self.assertTrue(result["review_prepared"], result)
        approval = json.loads((self.root / "09_approvals" / "APR_LOOKDEV_0001.json").read_text(encoding="utf-8"))
        self.assertEqual(2, sum(item["path"].endswith("storyboard.json") for item in approval["evidence"]))
        self.assertEqual(2, sum(item["path"].endswith("S01_P001.png") for item in approval["evidence"]))

    def test_decision_rebuilds_storyboard_mandatory_evidence_not_just_subject_pair(self) -> None:
        from prepare_review import prepare_review
        from record_decision import record_decision
        panel = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        panel.parent.mkdir(parents=True)
        panel.write_bytes(b"panel")
        board = self._write_reviewable_storyboard([("S01_P001", panel)])
        self.assertTrue(prepare_review(
            self.root, "STORYBOARD", "review_board", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(board), apply=True,
        )["review_prepared"])
        approval_path = self.root / "09_approvals" / "APR_STORYBOARD_0001.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["evidence"] = [item for item in approval["evidence"] if item["path"].endswith("storyboard.json")]
        write_json(approval_path, approval)
        result = record_decision(
            self.root, "APR_STORYBOARD_0001", "approve", actor="owner", reference="chat-2", notes=None,
            expected_project_sha256=sha256(self.project_path), expected_approval_sha256=sha256(approval_path),
            expected_subject_sha256=sha256(board), apply=True,
        )
        self.assertFalse(result["allowed"], result)

    def test_supporting_evidence_is_safe_deduplicated_and_mirrored_only_for_fixed_authorities(self) -> None:
        from prepare_review import prepare_review
        concept = self.root / "01_story" / "concept.png"
        concept.write_bytes(b"concept pixels")
        result = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story),
            supporting_evidence=("01_story/concept.png", "01_story/concept.png"), apply=True,
        )
        self.assertTrue(result["review_prepared"], result)
        approval = json.loads((self.root / "09_approvals" / "APR_STORY_0001.json").read_text(encoding="utf-8"))
        concept_pairs = [item for item in approval["evidence"] if item["path"].endswith("concept.png")]
        self.assertEqual(2, len(concept_pairs), concept_pairs)
        self.assertTrue((self.root / "01_story" / "history" / "story-contract" / "v001" / "evidence" / "01_story" / "concept.png").is_file())

        unsafe = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story),
            supporting_evidence=("../outside.png",), apply=False,
        )
        self.assertFalse(unsafe["allowed"])

    def test_prepare_rejects_a_name_redirecting_archive_ancestor_without_writing_through_it(self) -> None:
        from prepare_review import prepare_review
        history = self.root / "01_story" / "history"
        redirected = self.root / "redirected-history"
        redirected.mkdir()
        try:
            history.symlink_to(redirected, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        result = prepare_review(
            self.root, "STORY", "story-contract", requested_by="director",
            expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story), apply=True,
        )
        self.assertFalse(result["allowed"], result)
        self.assertFalse(any(redirected.rglob("*")), "must not write through an in-project redirect")

    def test_prepare_fails_closed_when_archive_detector_flags_an_existing_ancestor(self) -> None:
        from prepare_review import prepare_review
        (self.root / "01_story" / "history").mkdir()
        with patch("prepare_review._is_name_redirecting_reparse", side_effect=lambda path: path.name == "history"):
            result = prepare_review(
                self.root, "STORY", "story-contract", requested_by="director",
                expected_project_sha256=sha256(self.project_path), expected_subject_sha256=sha256(self.story), apply=True,
            )
        self.assertFalse(result["allowed"], result)
        self.assertFalse((self.root / "09_approvals").exists())

    def test_cli_help_is_available(self) -> None:
        for script in ("prepare_review.py", "record_decision.py"):
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / script), "--help"],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("usage:", completed.stdout.casefold())
