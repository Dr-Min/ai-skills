import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TransitionStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validate_project_patcher = patch(
            "validate_project.validate_project",
            return_value={
                "ok": True,
                "errors": [],
                "verification_scope": "OFFLINE_RECORD_CONSISTENCY",
                "remote_truth_verified": False,
            },
        )
        self.validate_project_patcher.start()
        self.receipt_patcher = patch(
            "transition_status.verify_decision_receipt", return_value=None
        )
        self.receipt_patcher.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.evidence = self.project / "01_story" / "STORY_CONTRACT.md"
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text("approved story", encoding="utf-8")
        self.hash = hashlib.sha256(self.evidence.read_bytes()).hexdigest()
        self.gates = {
            "STORY": "USER_REVIEW_REQUIRED",
            "STORYBOARD": "DRAFT",
            "LOOKDEV": "DRAFT",
            "ASSET_LOCK": "DRAFT",
            "SHOT_STILL": "DRAFT",
            "RAW_VIDEO": "DRAFT",
            "SOURCE_LIBRARY": "DRAFT",
            "EDIT": "DRAFT",
            "FINISH": "DRAFT",
        }
        self._write_project()
        self._write_approval("STORY", self.hash)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self.validate_project_patcher.stop()
        self.receipt_patcher.stop()

    def _write_project(self) -> None:
        write_json(
            self.project / "project.json",
            {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "current_stage": "STORY",
                "stage_gates": self.gates,
                "active_approval_ids": ["APR_STORY_0001"],
            },
        )

    def _write_approval(
        self,
        gate: str,
        digest: str,
        *,
        evidence_path: str = "01_story/STORY_CONTRACT.md",
        subject_id: str | None = None,
    ) -> None:
        subject_types = {
            "STORY": "STORY",
            "STORYBOARD": "STORYBOARD",
            "LOOKDEV": "LOOKDEV",
            "ASSET_LOCK": "ASSET",
            "SHOT_STILL": "SHOT_STILL",
            "RAW_VIDEO": "TAKE",
            "SOURCE_LIBRARY": "SOURCE_LIBRARY",
            "EDIT": "TIMELINE",
            "FINISH": "DELIVERY",
        }
        write_json(
            self.project / "09_approvals" / f"approval_{gate.lower()}.json",
            {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "approval_id": f"APR_{gate}_0001",
                "subject_type": subject_types[gate],
                "subject_id": subject_id
                or {"STORY": "story-contract", "LOOKDEV": "visual-bible"}.get(
                    gate, gate.lower()
                ),
                "subject_sha256": digest,
                "gate": gate,
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "project-owner",
                "decided_at": "2026-08-11T00:00:00Z",
                "user_evidence_reference": "chat-approval-0001",
                "evidence": [
                    {
                        "path": evidence_path,
                        "sha256": digest,
                        "verified_claim": "Visible story contract approved",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )

    def _write_finish_fixture(self) -> tuple[Path, Path]:
        for gate in self.gates:
            self.gates[gate] = "USER_APPROVED"
        self.gates["FINISH"] = "USER_REVIEW_REQUIRED"

        authority_bytes = {
            "STORY": (self.evidence, "story-contract", self.evidence.read_bytes()),
            "STORYBOARD": (
                self.project / "02_storyboard" / "storyboard.json",
                "storyboard",
                json.dumps(
                    {
                        "project_id": "take-me",
                        "storyboard_id": "storyboard",
                        "review_status": "USER_APPROVED",
                        "approval_id": "APR_STORYBOARD_0001",
                    }
                ).encode("utf-8"),
            ),
            "LOOKDEV": (
                self.project / "03_lookdev" / "VISUAL_BIBLE.md",
                "visual-bible",
                b"approved-lookdev",
            ),
        }
        for gate, (path, subject_id, content) in authority_bytes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self._write_approval(
                gate,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                evidence_path=str(path.relative_to(self.project)).replace("\\", "/"),
                subject_id=subject_id,
            )

        asset_master = self.project / "04_assets" / "masters" / "hero.png"
        asset_master.parent.mkdir(parents=True)
        asset_master.write_bytes(b"approved-asset")
        asset_hash = hashlib.sha256(asset_master.read_bytes()).hexdigest()
        write_json(
            self.project / "04_assets" / "records" / "hero" / "asset.json",
            {
                "project_id": "take-me",
                "asset_id": "hero",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_ASSET_LOCK_0001",
                "files": {
                    "immutable_master": {
                        "path": "04_assets/masters/hero.png",
                        "sha256": asset_hash,
                    }
                },
                "lineage": {"output_sha256": asset_hash},
            },
        )
        self._write_approval(
            "ASSET_LOCK",
            asset_hash,
            evidence_path="04_assets/masters/hero.png",
            subject_id="hero",
        )

        shot_path = self.project / "05_shots" / "S01_SH010" / "shot.json"
        write_json(
            shot_path,
            {
                "project_id": "take-me",
                "shot_id": "S01_SH010",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_SHOT_STILL_0001",
            },
        )
        shot_hash = hashlib.sha256(shot_path.read_bytes()).hexdigest()
        self._write_approval(
            "SHOT_STILL",
            shot_hash,
            evidence_path="05_shots/S01_SH010/shot.json",
            subject_id="S01_SH010",
        )

        take_output = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "out.mov"
        take_output.parent.mkdir(parents=True)
        take_output.write_bytes(b"approved-take")
        take_hash = hashlib.sha256(take_output.read_bytes()).hexdigest()
        write_json(
            take_output.parent / "take.json",
            {
                "project_id": "take-me",
                "take_id": "S01_SH010_T01",
                "shot_id": "S01_SH010",
                "review_status": "USER_APPROVED",
                "source_status": "SOURCE_APPROVED",
                "approval_id": "APR_RAW_VIDEO_0001",
                "output_file": "05_shots/S01_SH010/takes/S01_SH010_T01/out.mov",
                "output_sha256": take_hash,
            },
        )
        self._write_approval(
            "RAW_VIDEO",
            take_hash,
            evidence_path="05_shots/S01_SH010/takes/S01_SH010_T01/out.mov",
            subject_id="S01_SH010_T01",
        )

        source_manifest = self.project / "06_source_library" / "source_manifest.json"
        write_json(
            source_manifest,
            {
                "project_id": "take-me",
                "library_id": "source_library",
                "review_status": "USER_APPROVED",
                "lock_status": "SOURCE_LOCKED",
                "approval_id": "APR_SOURCE_LIBRARY_0001",
                "sources": [
                    {
                        "source_id": "SRC_S01_SH010_T01",
                        "take_id": "S01_SH010_T01",
                        "path": "05_shots/S01_SH010/takes/S01_SH010_T01/out.mov",
                        "sha256": take_hash,
                        "source_status": "SOURCE_APPROVED",
                    }
                ],
            },
        )
        source_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
        self._write_approval(
            "SOURCE_LIBRARY",
            source_hash,
            evidence_path="06_source_library/source_manifest.json",
            subject_id="source_library",
        )

        timeline_path = self.project / "07_edit" / "timeline.json"
        write_json(
            timeline_path,
            {
                "project_id": "take-me",
                "timeline_id": "picture_lock",
                "lock_status": "PICTURE_LOCKED",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_EDIT_0001",
            },
        )
        timeline_hash = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        self._write_approval(
            "EDIT",
            timeline_hash,
            evidence_path="07_edit/timeline.json",
            subject_id="picture_lock",
        )

        export_path = self.project / "08_delivery" / "masters" / "final.mov"
        export_path.parent.mkdir(parents=True)
        export_path.write_bytes(b"final-export")
        export_hash = hashlib.sha256(export_path.read_bytes()).hexdigest()
        qa_path = self.project / "08_delivery" / "qa" / "review-frame.png"
        qa_path.parent.mkdir(parents=True)
        qa_path.write_bytes(b"visible-qa-frame")
        qa_hash = hashlib.sha256(qa_path.read_bytes()).hexdigest()
        qa_evidence = [
            {
                "path": "08_delivery/qa/review-frame.png",
                "sha256": qa_hash,
                "verified_claim": "Visible delivery QA frame",
            }
        ]
        qa = {
            "overall_verdict": "PASS",
            **{
                name: {"status": "PASS", "evidence": qa_evidence, "reason": None}
                for name in (
                    "media_integrity",
                    "frame_integrity",
                    "audio_sync",
                    "crop_safety",
                    "rights_clearance",
                )
            },
        }
        delivery_path = self.project / "08_delivery" / "delivery.json"
        write_json(
            delivery_path,
            {
                "project_id": "take-me",
                "delivery_id": "final_delivery",
                "version": 1,
                "supersedes_delivery": None,
                "source_timeline": {
                    "timeline_id": "picture_lock",
                    "path": "07_edit/timeline.json",
                    "sha256": timeline_hash,
                },
                "export": {
                    "path": "08_delivery/masters/final.mov",
                    "sha256": export_hash,
                    "media": {"media_type": "VIDEO"},
                },
                "derivation": {
                    "execution_origin": "LOCAL_PROCESSING",
                    "tool": {"name": "ffmpeg", "version": "8", "verified": True},
                    "settings": {"codec": "prores"},
                    "input_hashes": [
                        {"path": "07_edit/timeline.json", "sha256": timeline_hash}
                    ],
                },
                "qa": qa,
                "review_status": "USER_APPROVED",
                "approval_id": "APR_FINISH_0001",
            },
        )
        delivery_hash = hashlib.sha256(delivery_path.read_bytes()).hexdigest()
        self._write_approval(
            "FINISH",
            delivery_hash,
            evidence_path=str(delivery_path.relative_to(self.project)).replace("\\", "/"),
            subject_id="final_delivery",
        )
        finish_approval_path = self.project / "09_approvals" / "approval_finish.json"
        finish_approval = json.loads(finish_approval_path.read_text(encoding="utf-8"))
        finish_approval["evidence"].extend(
            [
                {
                    "path": "08_delivery/masters/final.mov",
                    "sha256": export_hash,
                    "verified_claim": "Final export bytes",
                },
                qa_evidence[0],
            ]
        )
        write_json(finish_approval_path, finish_approval)

        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"] = {
            "story_contract": "01_story/STORY_CONTRACT.md",
            "storyboard": "02_storyboard/storyboard.json",
            "visual_bible": "03_lookdev/VISUAL_BIBLE.md",
            "asset_records_root": "04_assets/records",
            "source_manifest": "06_source_library/source_manifest.json",
            "timeline": "07_edit/timeline.json",
            "delivery_record": str(delivery_path.relative_to(self.project)).replace("\\", "/"),
        }
        project["active_approval_ids"] = [
            f"APR_{gate}_0001" for gate in self.gates if gate != "FINISH"
        ]
        write_json(project_path, project)
        return timeline_path, delivery_path

    def _write_story_through_lookdev_prerequisites(self) -> None:
        self.gates["STORY"] = "USER_APPROVED"
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard,
            {
                "project_id": "take-me",
                "storyboard_id": "storyboard",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
            },
        )
        self.gates["STORYBOARD"] = "USER_APPROVED"
        self._write_approval(
            "STORYBOARD",
            hashlib.sha256(storyboard.read_bytes()).hexdigest(),
            evidence_path="02_storyboard/storyboard.json",
        )
        visual_bible = self.project / "03_lookdev" / "VISUAL_BIBLE.md"
        visual_bible.parent.mkdir(parents=True, exist_ok=True)
        visual_bible.write_bytes(b"approved-lookdev")
        self.gates["LOOKDEV"] = "USER_APPROVED"
        self._write_approval(
            "LOOKDEV",
            hashlib.sha256(visual_bible.read_bytes()).hexdigest(),
            evidence_path="03_lookdev/VISUAL_BIBLE.md",
        )

    def _write_approved_asset(self, asset_id: str, approval_id: str) -> None:
        master = self.project / "04_assets" / "masters" / f"{asset_id}.png"
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(f"approved-{asset_id}".encode("utf-8"))
        digest = hashlib.sha256(master.read_bytes()).hexdigest()
        relative_master = str(master.relative_to(self.project)).replace("\\", "/")
        write_json(
            self.project / "04_assets" / "records" / asset_id / "asset.json",
            {
                "project_id": "take-me",
                "asset_id": asset_id,
                "review_status": "USER_APPROVED",
                "approval_id": approval_id,
                "files": {
                    "immutable_master": {"path": relative_master, "sha256": digest}
                },
                "lineage": {"output_sha256": digest},
            },
        )
        approval_path = self.project / "09_approvals" / f"approval_{asset_id}.json"
        write_json(
            approval_path,
            {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "approval_id": approval_id,
                "subject_type": "ASSET",
                "subject_id": asset_id,
                "subject_sha256": digest,
                "gate": "ASSET_LOCK",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "project-owner",
                "decided_at": "2026-08-11T00:00:00Z",
                "user_evidence_reference": f"chat-{asset_id}",
                "evidence": [
                    {
                        "path": relative_master,
                        "sha256": digest,
                        "verified_claim": f"Visible {asset_id} master",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )

    def _promote_finish_delivery_to_v2(self) -> Path:
        v1_path = self.project / "08_delivery" / "delivery.json"
        v1_payload = json.loads(v1_path.read_text(encoding="utf-8"))
        v1_hash = hashlib.sha256(v1_path.read_bytes()).hexdigest()
        old_approval_path = self.project / "09_approvals" / "approval_finish.json"
        old_approval = json.loads(old_approval_path.read_text(encoding="utf-8"))
        old_approval["superseded_by_approval_id"] = "APR_FINISH_0002"
        write_json(
            self.project / "09_approvals" / "approval_finish_v001.json",
            old_approval,
        )
        old_approval_path.unlink()

        v2_path = (
            self.project
            / "08_delivery"
            / "records"
            / "final_delivery"
            / "v002"
            / "delivery.json"
        )
        v2_payload = dict(v1_payload)
        v2_payload["version"] = 2
        v2_payload["supersedes_delivery"] = {
            "delivery_id": "final_delivery",
            "version": 1,
            "path": "08_delivery/delivery.json",
            "sha256": v1_hash,
            "approval_id": "APR_FINISH_0001",
        }
        v2_payload["approval_id"] = "APR_FINISH_0002"
        write_json(v2_path, v2_payload)
        v2_hash = hashlib.sha256(v2_path.read_bytes()).hexdigest()

        new_approval = dict(old_approval)
        new_approval["approval_id"] = "APR_FINISH_0002"
        new_approval["subject_sha256"] = v2_hash
        new_approval["supersedes_approval_id"] = "APR_FINISH_0001"
        new_approval["superseded_by_approval_id"] = None
        new_approval["evidence"] = [dict(item) for item in old_approval["evidence"]]
        new_approval["evidence"][0] = {
            "path": "08_delivery/records/final_delivery/v002/delivery.json",
            "sha256": v2_hash,
            "verified_claim": "Current immutable v2 delivery record",
        }
        write_json(
            self.project / "09_approvals" / "approval_finish_v002.json",
            new_approval,
        )

        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["delivery_record"] = (
            "08_delivery/records/final_delivery/v002/delivery.json"
        )
        write_json(project_path, project)
        return v2_path

    def test_allows_approval_only_with_valid_evidence_hash(self) -> None:
        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertTrue(result["allowed"], result)

        auxiliary = self.project / "01_story" / "story_review.png"
        auxiliary.write_bytes(b"ui-screenshot")
        auxiliary_hash = hashlib.sha256(auxiliary.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["evidence"].append(
            {
                "path": "01_story/story_review.png",
                "sha256": auxiliary_hash,
                "verified_claim": "approval UI evidence",
            }
        )
        write_json(approval_path, approval)
        auxiliary_result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertTrue(auxiliary_result["allowed"], auxiliary_result)

        self.evidence.write_text("changed later", encoding="utf-8")
        mismatch = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertIn(
            "E_APPROVAL_HASH_MISMATCH",
            {item["code"] for item in mismatch["errors"]},
        )

    def test_fails_closed_when_previous_stage_is_not_approved(self) -> None:
        self.gates["STORY"] = "DRAFT"
        self.gates["STORYBOARD"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        self._write_approval("STORYBOARD", self.hash)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORYBOARD", "USER_APPROVED")
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_transition_propagates_full_project_preflight_failures(self) -> None:
        from transition_status import evaluate_transition

        preflight_error = {
            "code": "SCHEMA_ERROR",
            "message": "delivery schema contract is invalid",
            "path": "08_delivery/delivery.json",
        }
        with patch(
            "validate_project.validate_project",
            return_value={
                "ok": False,
                "errors": [preflight_error],
                "verification_scope": "OFFLINE_RECORD_CONSISTENCY",
                "remote_truth_verified": False,
            },
        ), patch(
            "transition_status._read_records",
            side_effect=AssertionError("gate-specific evaluation ran after failed preflight"),
        ) as read_records:
            result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertIn(preflight_error, result["errors"])
        read_records.assert_not_called()

    def test_scalar_project_json_is_rejected_without_a_traceback(self) -> None:
        from transition_status import apply_transition, evaluate_transition

        project_path = self.project / "project.json"
        project_path.write_text("[]", encoding="utf-8")
        digest = hashlib.sha256(project_path.read_bytes()).hexdigest()

        evaluated = evaluate_transition(self.project, "STORY", "USER_REVIEW_REQUIRED")
        applied = apply_transition(
            self.project,
            "STORY",
            "USER_REVIEW_REQUIRED",
            expected_project_sha256=digest,
        )

        self.assertFalse(evaluated["allowed"], evaluated)
        self.assertFalse(applied["applied"], applied)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in applied["errors"]})

    def test_dry_run_transition_has_a_fail_closed_public_boundary(self) -> None:
        from transition_status import evaluate_transition

        with patch(
            "transition_status._read_records",
            side_effect=OSError("record disappeared during discovery"),
        ):
            result = evaluate_transition(self.project, "STORY", "USER_REVIEW_REQUIRED")

        self.assertFalse(result["allowed"], result)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_later_gate_rejects_an_approved_prerequisite_without_active_approval(self) -> None:
        self.gates["STORY"] = "USER_APPROVED"
        self.gates["STORYBOARD"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = []
        write_json(project_path, project)
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard,
            {
                "project_id": "take-me",
                "storyboard_id": "storyboard",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
            },
        )
        storyboard_hash = hashlib.sha256(storyboard.read_bytes()).hexdigest()
        self._write_approval(
            "STORYBOARD",
            storyboard_hash,
            evidence_path="02_storyboard/storyboard.json",
        )

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORYBOARD", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})
        self.assertTrue(any("active" in item["message"].casefold() for item in result["errors"]), result)

    def test_prerequisite_gate_requires_exactly_one_active_concrete_approval(self) -> None:
        self.gates["STORY"] = "USER_APPROVED"
        self.gates["STORYBOARD"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard,
            {
                "project_id": "take-me",
                "storyboard_id": "storyboard",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
            },
        )
        storyboard_hash = hashlib.sha256(storyboard.read_bytes()).hexdigest()
        self._write_approval(
            "STORYBOARD",
            storyboard_hash,
            evidence_path="02_storyboard/storyboard.json",
        )
        duplicate = json.loads(
            (self.project / "09_approvals" / "approval_story.json").read_text(encoding="utf-8")
        )
        duplicate["approval_id"] = "APR_STORY_0002"
        write_json(self.project / "09_approvals" / "approval_story_duplicate.json", duplicate)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = ["APR_STORY_0001", "APR_STORY_0002"]
        write_json(project_path, project)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORYBOARD", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertTrue(any("exactly one active" in item["message"].casefold() for item in result["errors"]), result)

    def test_collection_gate_atomically_activates_every_current_record_approval(self) -> None:
        self._write_story_through_lookdev_prerequisites()
        self.gates["ASSET_LOCK"] = "USER_REVIEW_REQUIRED"
        self._write_approved_asset("hero", "APR_ASSET_HERO_0001")
        self._write_approved_asset("moon", "APR_ASSET_MOON_0001")
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = [
            "APR_STORY_0001",
            "APR_STORYBOARD_0001",
            "APR_LOOKDEV_0001",
        ]
        write_json(project_path, project)

        from transition_status import apply_transition

        expected = hashlib.sha256(project_path.read_bytes()).hexdigest()
        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            result = apply_transition(
                self.project,
                "ASSET_LOCK",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )
        self.assertTrue(result.get("applied"), result)
        updated = json.loads(project_path.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "APR_STORY_0001",
                "APR_STORYBOARD_0001",
                "APR_LOOKDEV_0001",
                "APR_ASSET_HERO_0001",
                "APR_ASSET_MOON_0001",
            },
            set(updated["active_approval_ids"]),
        )

    def test_collection_gate_rejects_a_missing_record_approval(self) -> None:
        self._write_story_through_lookdev_prerequisites()
        self.gates["ASSET_LOCK"] = "USER_REVIEW_REQUIRED"
        self._write_approved_asset("hero", "APR_ASSET_HERO_0001")
        self._write_approved_asset("moon", "APR_ASSET_MOON_0001")
        (self.project / "09_approvals" / "approval_moon.json").unlink()
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = [
            "APR_STORY_0001",
            "APR_STORYBOARD_0001",
            "APR_LOOKDEV_0001",
        ]
        write_json(project_path, project)

        from transition_status import evaluate_transition

        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            result = evaluate_transition(self.project, "ASSET_LOCK", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertTrue(
            any("moon" in item["message"].casefold() for item in result["errors"]),
            result,
        )

    def test_cross_project_approval_is_never_selected(self) -> None:
        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["project_id"] = "another-project"
        write_json(approval_path, approval)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertIsNone(result["selected_approval_id"])
        self.assertIn("E_UNAPPROVED_INPUT", {item["code"] for item in result["errors"]})

    def test_requires_verified_remote_proof_for_approved_video(self) -> None:
        for gate in ("STORY", "STORYBOARD", "LOOKDEV", "ASSET_LOCK", "SHOT_STILL"):
            self.gates[gate] = "USER_APPROVED"
        self.gates["RAW_VIDEO"] = "USER_REVIEW_REQUIRED"
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        storyboard.parent.mkdir(parents=True)
        storyboard.write_bytes(b"approved-storyboard")
        self._write_approval(
            "STORYBOARD",
            hashlib.sha256(storyboard.read_bytes()).hexdigest(),
            evidence_path="02_storyboard/storyboard.json",
        )
        visual_bible = self.project / "03_lookdev" / "VISUAL_BIBLE.md"
        visual_bible.parent.mkdir(parents=True)
        visual_bible.write_bytes(b"approved-lookdev")
        self._write_approval(
            "LOOKDEV",
            hashlib.sha256(visual_bible.read_bytes()).hexdigest(),
            evidence_path="03_lookdev/VISUAL_BIBLE.md",
        )
        asset_master = self.project / "04_assets" / "masters" / "hero.png"
        asset_master.parent.mkdir(parents=True)
        asset_master.write_bytes(b"approved-asset")
        asset_hash = hashlib.sha256(asset_master.read_bytes()).hexdigest()
        write_json(
            self.project / "04_assets" / "records" / "hero" / "asset.json",
            {
                "asset_id": "hero",
                "files": {
                    "immutable_master": {
                        "path": "04_assets/masters/hero.png",
                        "sha256": asset_hash,
                    }
                },
                "lineage": {"output_sha256": asset_hash},
            },
        )
        self._write_approval(
            "ASSET_LOCK",
            asset_hash,
            evidence_path="04_assets/masters/hero.png",
            subject_id="hero",
        )
        shot_path = self.project / "05_shots" / "S01_SH010" / "shot.json"
        write_json(shot_path, {"shot_id": "S01_SH010", "review_status": "USER_APPROVED"})
        self._write_approval(
            "SHOT_STILL",
            hashlib.sha256(shot_path.read_bytes()).hexdigest(),
            evidence_path="05_shots/S01_SH010/shot.json",
            subject_id="S01_SH010",
        )
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = [
            "APR_STORY_0001",
            "APR_STORYBOARD_0001",
            "APR_LOOKDEV_0001",
            "APR_ASSET_LOCK_0001",
            "APR_SHOT_STILL_0001",
        ]
        write_json(project_path, project)
        output = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "out.mov"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"unverified-remote-output")
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        self._write_approval(
            "RAW_VIDEO",
            output_hash,
            evidence_path=str(output.relative_to(self.project)).replace("\\", "/"),
            subject_id="S01_SH010_T01",
        )
        write_json(
            self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "take.json",
            {
                "project_id": "take-me",
                "take_id": "S01_SH010_T01",
                "shot_id": "S01_SH010",
                "coverage_requirement_ids": ["COV_REMOTE_PROOF"],
                "execution_origin": "REMOTE_GENERATION",
                "remote_job_id": None,
                "output_file": str(output.relative_to(self.project)).replace("\\", "/"),
                "output_sha256": output_hash,
                "input_hashes": [
                    {
                        "path": str(self.evidence.relative_to(self.project)).replace("\\", "/"),
                        "sha256": self.hash,
                    }
                ],
                "model": {"provider": "HIGGSFIELD", "name": "Seedance", "version": "2", "verified": True},
                "remote": {"verified": False, "job_id": None},
                "diagnosis": {"verdict": "PASS", "first_failure": None, "what_held": ["identity"]},
            },
        )

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "RAW_VIDEO", "USER_APPROVED")
        self.assertIn("E_REMOTE_PROOF_MISSING", {item["code"] for item in result["errors"]})
        self.assertFalse(result["remote_truth_verified"])
        self.assertEqual("OFFLINE_RECORD_CONSISTENCY", result["verification_scope"])

    def test_edit_requires_a_locked_approved_source_library(self) -> None:
        for gate in ("STORY", "STORYBOARD", "LOOKDEV", "ASSET_LOCK", "SHOT_STILL", "RAW_VIDEO", "SOURCE_LIBRARY"):
            self.gates[gate] = "USER_APPROVED"
        self.gates["EDIT"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        self._write_approval("EDIT", self.hash)
        write_json(
            self.project / "06_source_library" / "source_manifest.json",
            {"review_status": "USER_APPROVED", "lock_status": "UNLOCKED", "sources": []},
        )

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "EDIT", "USER_APPROVED")
        self.assertIn("E_SOURCE_LIBRARY_UNLOCKED", {item["code"] for item in result["errors"]})

    def test_edit_rejects_locked_source_not_bound_to_an_approved_take(self) -> None:
        for gate in ("STORY", "STORYBOARD", "LOOKDEV", "ASSET_LOCK", "SHOT_STILL", "RAW_VIDEO", "SOURCE_LIBRARY"):
            self.gates[gate] = "USER_APPROVED"
        self.gates["EDIT"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        self._write_approval("EDIT", self.hash)
        self._write_approval("SOURCE_LIBRARY", self.hash)
        media = self.project / "06_source_library" / "approved_video" / "orphan.mov"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"orphan-source")
        digest = hashlib.sha256(media.read_bytes()).hexdigest()
        write_json(
            self.project / "06_source_library" / "source_manifest.json",
            {
                "review_status": "USER_APPROVED",
                "lock_status": "SOURCE_LOCKED",
                "approval_id": "APR_SOURCE_LIBRARY_0001",
                "sources": [
                    {
                        "source_id": "SRC_ORPHAN",
                        "take_id": "S01_SH999_T01",
                        "path": "06_source_library/approved_video/orphan.mov",
                        "sha256": digest,
                        "source_status": "SOURCE_APPROVED",
                    }
                ],
            },
        )

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "EDIT", "USER_APPROVED")
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_UNAPPROVED_INPUT", codes)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", codes)

    def test_accepts_hash_backed_local_processing_without_fake_remote_proof(self) -> None:
        for gate in ("STORY", "STORYBOARD", "LOOKDEV", "ASSET_LOCK", "SHOT_STILL"):
            self.gates[gate] = "USER_APPROVED"
        self.gates["RAW_VIDEO"] = "USER_REVIEW_REQUIRED"
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard,
            {
                "project_id": "take-me",
                "storyboard_id": "storyboard",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
            },
        )
        self._write_approval(
            "STORYBOARD",
            hashlib.sha256(storyboard.read_bytes()).hexdigest(),
            evidence_path="02_storyboard/storyboard.json",
        )
        visual_bible = self.project / "03_lookdev" / "VISUAL_BIBLE.md"
        visual_bible.parent.mkdir(parents=True)
        visual_bible.write_bytes(b"approved-lookdev")
        self._write_approval(
            "LOOKDEV",
            hashlib.sha256(visual_bible.read_bytes()).hexdigest(),
            evidence_path="03_lookdev/VISUAL_BIBLE.md",
        )
        asset_master = self.project / "04_assets" / "masters" / "hero.png"
        asset_master.parent.mkdir(parents=True)
        asset_master.write_bytes(b"approved-asset")
        asset_hash = hashlib.sha256(asset_master.read_bytes()).hexdigest()
        write_json(
            self.project / "04_assets" / "records" / "hero" / "asset.json",
            {
                "project_id": "take-me",
                "asset_id": "hero",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_ASSET_LOCK_0001",
                "files": {
                    "immutable_master": {
                        "path": "04_assets/masters/hero.png",
                        "sha256": asset_hash,
                    }
                },
                "lineage": {"output_sha256": asset_hash},
            },
        )
        self._write_approval(
            "ASSET_LOCK",
            asset_hash,
            evidence_path="04_assets/masters/hero.png",
            subject_id="hero",
        )
        shot_path = self.project / "05_shots" / "S01_SH010" / "shot.json"
        write_json(
            shot_path,
            {
                "project_id": "take-me",
                "shot_id": "S01_SH010",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_SHOT_STILL_0001",
            },
        )
        self._write_approval(
            "SHOT_STILL",
            hashlib.sha256(shot_path.read_bytes()).hexdigest(),
            evidence_path="05_shots/S01_SH010/shot.json",
            subject_id="S01_SH010",
        )
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = [
            "APR_STORY_0001",
            "APR_STORYBOARD_0001",
            "APR_LOOKDEV_0001",
            "APR_ASSET_LOCK_0001",
            "APR_SHOT_STILL_0001",
        ]
        write_json(project_path, project)
        self._write_approval("RAW_VIDEO", self.hash)
        input_file = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T00" / "raw.mov"
        output_file = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "clean.mov"
        input_file.parent.mkdir(parents=True)
        output_file.parent.mkdir(parents=True)
        input_file.write_bytes(b"camera-original")
        output_file.write_bytes(b"local-transcode")
        input_hash = hashlib.sha256(input_file.read_bytes()).hexdigest()
        output_hash = hashlib.sha256(output_file.read_bytes()).hexdigest()
        write_json(
            input_file.parent / "take.json",
            {
                "project_id": "take-me",
                "take_id": "S01_SH010_T00",
                "shot_id": "S01_SH010",
                "execution_origin": "LOCAL_PROCESSING",
                "source_status": "RAW",
                "review_status": "EXCLUDED_FROM_INPUTS",
                "model": {"provider": "LOCAL", "name": "camera import", "version": "1", "verified": True},
                "generation_parameters": {"operation": "import"},
                "remote_job_id": None,
                "remote_url": None,
                "remote": {"project_id": None, "job_id": None, "verified": False, "verified_at": None, "evidence": []},
                "input_hashes": [],
                "output_file": str(input_file.relative_to(self.project)).replace("\\", "/"),
                "output_sha256": input_hash,
                "lineage": {"parent_take_id": None, "source_take_ids": [], "source_asset_ids": [], "derivation": "GENERATED"},
                "diagnosis": {"verdict": "NOT_REVIEWED", "what_held": []},
            },
        )
        write_json(
            output_file.parent / "take.json",
            {
                "project_id": "take-me",
                "take_id": "S01_SH010_T01",
                "shot_id": "S01_SH010",
                "coverage_requirement_ids": ["COV_LOCAL_TRANSCODE"],
                "execution_origin": "LOCAL_PROCESSING",
                "model": {"provider": "LOCAL", "name": "ffmpeg", "version": "8.0", "verified": True},
                "generation_parameters": {"codec": "prores"},
                "remote_job_id": None,
                "remote_url": None,
                "remote": {"project_id": None, "job_id": None, "verified": False, "verified_at": None, "evidence": []},
                "input_hashes": [{"path": str(input_file.relative_to(self.project)).replace("\\", "/"), "sha256": input_hash}],
                "output_file": str(output_file.relative_to(self.project)).replace("\\", "/"),
                "output_sha256": output_hash,
                "lineage": {"parent_take_id": "S01_SH010_T00", "source_take_ids": ["S01_SH010_T00"], "source_asset_ids": [], "derivation": "TRANSCODE"},
                "diagnosis": {"verdict": "PASS", "first_failure": None, "what_held": ["identity", "timing"]},
            },
        )
        self._write_approval(
            "RAW_VIDEO",
            output_hash,
            evidence_path=str(output_file.relative_to(self.project)).replace("\\", "/"),
            subject_id="S01_SH010_T01",
        )

        from transition_status import evaluate_transition

        with (
            patch("validate_references.validate_references", return_value={"ok": True, "errors": []}),
            patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}),
        ):
            result = evaluate_transition(self.project, "RAW_VIDEO", "USER_APPROVED")
        self.assertTrue(result["allowed"], result)

    def test_public_error_code_contract_is_complete(self) -> None:
        from transition_status import ERROR_CODES

        required = {
            "E_STAGE_PREREQ",
            "E_UNAPPROVED_INPUT",
            "E_EXCLUDED_INPUT",
            "E_MUTEX_REFERENCE",
            "E_REFERENCE_ROLE_CONFLICT",
            "E_APPROVAL_HASH_MISMATCH",
            "E_DERIVATIVE_AS_EDIT_BASE",
            "E_REMOTE_PROOF_MISSING",
            "E_SOURCE_LIBRARY_UNLOCKED",
        }
        self.assertTrue(required.issubset(ERROR_CODES))

    def test_malformed_local_input_hash_fails_closed_without_crashing(self) -> None:
        from transition_status import _check_video_proof

        output = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "out.mov"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"output")
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        take_path = output.parent / "take.json"
        take = {
            "project_id": "take-me",
            "take_id": "S01_SH010_T01",
            "shot_id": "S01_SH010",
            "coverage_requirement_ids": ["COV_LOCAL"],
            "execution_origin": "LOCAL_PROCESSING",
            "model": {"name": "ffmpeg", "version": "8", "verified": True},
            "generation_parameters": {"codec": "prores"},
            "remote_job_id": None,
            "remote_url": None,
            "remote": {"verified": False, "job_id": None},
            "input_hashes": ["not-an-object"],
            "output_file": str(output.relative_to(self.project)).replace("\\", "/"),
            "output_sha256": output_hash,
            "lineage": {"parent_take_id": "S01_SH010_T00"},
            "diagnosis": {"verdict": "PASS", "first_failure": None, "what_held": ["timing"]},
        }
        write_json(take_path, take)
        self._write_approval(
            "RAW_VIDEO",
            output_hash,
            evidence_path=str(output.relative_to(self.project)).replace("\\", "/"),
            subject_id="S01_SH010_T01",
        )
        approval_path = self.project / "09_approvals" / "approval_raw_video.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        errors: list[dict] = []
        _check_video_proof(
            self.project,
            {"project_id": "take-me"},
            [
                (take, take_path),
                (approval, approval_path),
            ],
            errors,
        )
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in errors})

    def test_apply_uses_expected_hash_and_synchronizes_selected_approval(self) -> None:
        from transition_status import apply_transition

        project_path = self.project / "project.json"
        before_hash = hashlib.sha256(project_path.read_bytes()).hexdigest()
        result = apply_transition(
            self.project,
            "STORY",
            "USER_APPROVED",
            expected_project_sha256=before_hash,
        )
        self.assertTrue(result["applied"], result)
        updated = json.loads(project_path.read_text(encoding="utf-8"))
        self.assertEqual("USER_APPROVED", updated["stage_gates"]["STORY"])
        self.assertEqual("STORYBOARD", updated["current_stage"])
        self.assertIn("APR_STORY_0001", updated["active_approval_ids"])

        stale = apply_transition(
            self.project,
            "STORY",
            "USER_APPROVED",
            expected_project_sha256=before_hash,
        )
        self.assertFalse(stale["applied"])
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in stale["errors"]})

    def test_finish_requires_active_user_approvals_for_every_stage(self) -> None:
        for gate in self.gates:
            self.gates[gate] = "USER_APPROVED"
        self.gates["FINISH"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        self._write_approval("FINISH", self.hash)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_story_approval_cannot_bind_only_to_a_stale_copy(self) -> None:
        stale = self.project / "01_story" / "stale.md"
        stale.write_text("old story", encoding="utf-8")
        stale_hash = hashlib.sha256(stale.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["subject_type"] = "STORY"
        approval["subject_id"] = "story-contract"
        approval["subject_sha256"] = stale_hash
        approval["evidence"] = [{"path": "01_story/stale.md", "sha256": stale_hash}]
        write_json(approval_path, approval)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})

    def test_approval_evidence_must_bind_the_exact_authority_path_even_when_bytes_match(self) -> None:
        alias = self.project / "01_story" / "same-bytes-copy.md"
        alias.write_bytes(self.evidence.read_bytes())
        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["evidence"] = [
            {
                "path": "01_story/same-bytes-copy.md",
                "sha256": self.hash,
                "verified_claim": "Wrong path with identical bytes",
            }
        ]
        write_json(approval_path, approval)

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})

    def test_story_and_lookdev_require_their_fixed_prose_subject_ids(self) -> None:
        from transition_status import evaluate_transition

        story_approval_path = self.project / "09_approvals" / "approval_story.json"
        story_approval = json.loads(story_approval_path.read_text(encoding="utf-8"))
        story_approval["subject_id"] = "arbitrary-story"
        write_json(story_approval_path, story_approval)
        story_result = evaluate_transition(self.project, "STORY", "USER_APPROVED")
        self.assertFalse(story_result["allowed"], story_result)
        self.assertTrue(
            any("story-contract" in item["message"] for item in story_result["errors"]),
            story_result,
        )

        self._write_approval("STORY", self.hash)
        self._write_story_through_lookdev_prerequisites()
        self.gates["LOOKDEV"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = ["APR_STORY_0001", "APR_STORYBOARD_0001"]
        write_json(project_path, project)
        lookdev_approval_path = self.project / "09_approvals" / "approval_lookdev.json"
        lookdev_approval = json.loads(lookdev_approval_path.read_text(encoding="utf-8"))
        lookdev_approval["subject_id"] = "arbitrary-look"
        write_json(lookdev_approval_path, lookdev_approval)
        lookdev_result = evaluate_transition(self.project, "LOOKDEV", "USER_APPROVED")
        self.assertFalse(lookdev_result["allowed"], lookdev_result)
        self.assertTrue(
            any("visual-bible" in item["message"] for item in lookdev_result["errors"]),
            lookdev_result,
        )

    def test_asset_lock_propagates_all_lineage_failures(self) -> None:
        for gate in ("STORY", "STORYBOARD", "LOOKDEV"):
            self.gates[gate] = "USER_APPROVED"
        self.gates["ASSET_LOCK"] = "USER_REVIEW_REQUIRED"
        self._write_project()
        self._write_approval("ASSET_LOCK", self.hash)
        write_json(
            self.project / "04_assets" / "records" / "missing_master" / "asset.json",
            {
                "asset_id": "missing_master",
                "review_status": "USER_APPROVED",
                "approval_id": None,
                "files": {"immutable_master": {"path": "04_assets/missing.png", "sha256": "a" * 64}},
                "lineage": {"derivation": "IMPORTED", "output_sha256": "a" * 64},
            },
        )

        from transition_status import evaluate_transition

        result = evaluate_transition(self.project, "ASSET_LOCK", "USER_APPROVED")
        self.assertFalse(result["allowed"])
        self.assertTrue(
            {"APPROVAL_HASH_MISSING", "LINEAGE_FILE_MISSING"}
            & {item["code"] for item in result["errors"]}
        )

    def test_concurrent_apply_has_exactly_one_compare_and_swap_winner(self) -> None:
        from transition_status import apply_transition

        project_path = self.project / "project.json"
        expected = hashlib.sha256(project_path.read_bytes()).hexdigest()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: apply_transition(
                        self.project,
                        "STORY",
                        "USER_APPROVED",
                        expected_project_sha256=expected,
                    ),
                    range(2),
                )
            )
        self.assertEqual(1, sum(result.get("applied") is True for result in results), results)

    def test_transition_lock_does_not_follow_the_project_logs_junction(self) -> None:
        outside_temp = tempfile.TemporaryDirectory()
        outside = Path(outside_temp.name)
        logs = self.project / "99_logs"
        if os.name == "nt":
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(logs), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if created.returncode != 0:
                outside_temp.cleanup()
                self.skipTest(f"junction creation unavailable: {created.stderr}")
        else:
            logs.symlink_to(outside, target_is_directory=True)
        try:
            from transition_status import apply_transition

            project_path = self.project / "project.json"
            expected = hashlib.sha256(project_path.read_bytes()).hexdigest()
            result = apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )

            self.assertTrue(result.get("applied"), result)
            self.assertEqual([], list(outside.iterdir()), "transition lock escaped the project root")
            self.assertTrue((self.project / ".cinema-transition.lock").is_file())
        finally:
            try:
                logs.rmdir()
            except OSError:
                pass
            outside_temp.cleanup()

    def test_transition_lock_rejects_an_existing_symlink(self) -> None:
        outside_temp = tempfile.TemporaryDirectory()
        outside = Path(outside_temp.name) / "outside.lock"
        outside.write_bytes(b"outside-must-not-change")
        lock_path = self.project / ".cinema-transition.lock"
        try:
            lock_path.symlink_to(outside)
        except OSError as exc:
            outside_temp.cleanup()
            self.skipTest(f"symlink creation unavailable: {exc}")
        try:
            from transition_status import apply_transition

            project_path = self.project / "project.json"
            before_project = project_path.read_bytes()
            expected = hashlib.sha256(before_project).hexdigest()
            result = apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )

            self.assertFalse(result.get("applied"), result)
            self.assertEqual(b"outside-must-not-change", outside.read_bytes())
            self.assertEqual(before_project, project_path.read_bytes())
        finally:
            lock_path.unlink(missing_ok=True)
            outside_temp.cleanup()

    def test_transition_lock_rejects_an_existing_reparse_directory(self) -> None:
        outside_temp = tempfile.TemporaryDirectory()
        outside = Path(outside_temp.name)
        lock_path = self.project / ".cinema-transition.lock"
        if os.name == "nt":
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(lock_path), str(outside)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if created.returncode != 0:
                outside_temp.cleanup()
                self.skipTest(f"junction creation unavailable: {created.stderr}")
        else:
            lock_path.symlink_to(outside, target_is_directory=True)
        try:
            from transition_status import apply_transition

            project_path = self.project / "project.json"
            before_project = project_path.read_bytes()
            result = apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=hashlib.sha256(before_project).hexdigest(),
            )
            self.assertFalse(result.get("applied"), result)
            self.assertEqual([], list(outside.iterdir()))
            self.assertEqual(before_project, project_path.read_bytes())
        finally:
            try:
                lock_path.rmdir()
            except OSError:
                pass
            outside_temp.cleanup()

    def test_transition_lock_rejects_an_existing_hardlink_alias(self) -> None:
        outside_temp = tempfile.TemporaryDirectory()
        outside = Path(outside_temp.name) / "outside.lock"
        outside.write_bytes(b"")
        lock_path = self.project / ".cinema-transition.lock"
        try:
            os.link(outside, lock_path)
        except OSError as exc:
            outside_temp.cleanup()
            self.skipTest(f"hardlink creation unavailable: {exc}")
        try:
            from transition_status import apply_transition

            project_path = self.project / "project.json"
            before_project = project_path.read_bytes()
            result = apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=hashlib.sha256(before_project).hexdigest(),
            )
            self.assertFalse(result.get("applied"), result)
            self.assertEqual(b"", outside.read_bytes(), "lock initialization mutated an alias")
            self.assertEqual(before_project, project_path.read_bytes())
        finally:
            lock_path.unlink(missing_ok=True)
            outside_temp.cleanup()

    def test_transition_lock_allows_non_redirecting_cloud_placeholder_reparse(self) -> None:
        from transition_status import _transition_lock

        lock_path = self.project / ".cinema-transition.lock"
        lock_path.write_bytes(b"\0")
        real_lstat = os.lstat

        def cloud_placeholder_lstat(path):
            actual = real_lstat(path)
            return SimpleNamespace(
                st_mode=actual.st_mode,
                st_nlink=actual.st_nlink,
                st_dev=actual.st_dev,
                st_ino=actual.st_ino,
                st_size=actual.st_size,
                st_file_attributes=0x400,
                st_reparse_tag=0x9000001A,
            )

        with patch(
            "transition_status.os.lstat", side_effect=cloud_placeholder_lstat
        ), patch(
            "transition_status.is_name_redirecting_reparse", return_value=False
        ):
            with _transition_lock(self.project):
                pass

    def test_dependency_digest_cas_rejects_evidence_changed_after_second_evaluation(self) -> None:
        import transition_status

        project_path = self.project / "project.json"
        before_project = project_path.read_bytes()
        expected = hashlib.sha256(before_project).hexdigest()
        original_evaluate = transition_status.evaluate_transition
        call_count = 0

        def mutate_after_second_evaluation(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = original_evaluate(*args, **kwargs)
            if call_count == 2:
                self.evidence.write_text("mutated after evaluation", encoding="utf-8")
            return result

        with patch.object(transition_status, "evaluate_transition", side_effect=mutate_after_second_evaluation):
            result = transition_status.apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )

        self.assertEqual(2, call_count)
        self.assertFalse(result.get("applied"), result)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})
        self.assertEqual(before_project, project_path.read_bytes())

    def test_dependency_mutation_during_project_publish_rolls_back_the_transition(self) -> None:
        import transition_status

        project_path = self.project / "project.json"
        before_project = project_path.read_bytes()
        expected = hashlib.sha256(before_project).hexdigest()
        real_write_json = transition_status.write_json

        def mutate_dependency_during_staging(path, payload, *, force=False):
            self.evidence.write_text("mutated during project publication", encoding="utf-8")
            return real_write_json(path, payload, force=force)

        with patch.object(
            transition_status,
            "write_json",
            side_effect=mutate_dependency_during_staging,
        ):
            result = transition_status.apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )

        self.assertFalse(result.get("applied"), result)
        self.assertIn(
            "E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]}
        )
        self.assertEqual(
            before_project,
            project_path.read_bytes(),
            "a dependency race must not leave a promoted project on disk",
        )

    def test_competing_project_write_during_staging_is_preserved(self) -> None:
        import transition_status

        project_path = self.project / "project.json"
        expected = hashlib.sha256(project_path.read_bytes()).hexdigest()
        competitor = b'{"project_id":"competing-writer"}'
        real_replace = transition_status.os.replace

        def compete_after_publication(source, destination):
            result = real_replace(source, destination)
            project_path.write_bytes(competitor)
            return result

        with patch.object(
            transition_status.os, "replace", side_effect=compete_after_publication
        ):
            result = transition_status.apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=expected,
            )

        self.assertFalse(result.get("applied"), result)
        self.assertEqual(competitor, project_path.read_bytes())

    def test_dependency_cas_tracks_schema_snapshot_bytes(self) -> None:
        import transition_status

        schema_path = self.project / "00_schemas" / "project.schema.json"
        write_json(schema_path, {"type": "object"})
        project_path = self.project / "project.json"
        before_project = project_path.read_bytes()
        original_evaluate = transition_status.evaluate_transition
        call_count = 0

        def mutate_schema_after_second_evaluation(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = original_evaluate(*args, **kwargs)
            if call_count == 2:
                write_json(schema_path, {"type": "array"})
            return result

        with patch.object(
            transition_status,
            "evaluate_transition",
            side_effect=mutate_schema_after_second_evaluation,
        ):
            result = transition_status.apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=hashlib.sha256(before_project).hexdigest(),
            )
        self.assertFalse(result.get("applied"), result)
        self.assertEqual(before_project, project_path.read_bytes())

    def test_dependency_cas_tracks_new_delivery_history_records(self) -> None:
        import transition_status

        project_path = self.project / "project.json"
        before_project = project_path.read_bytes()
        added_history = (
            self.project
            / "08_delivery"
            / "records"
            / "final_delivery"
            / "v099"
            / "delivery.json"
        )
        original_evaluate = transition_status.evaluate_transition
        call_count = 0

        def add_history_after_second_evaluation(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = original_evaluate(*args, **kwargs)
            if call_count == 2:
                write_json(added_history, {"delivery_id": "final_delivery", "version": 99})
            return result

        with patch.object(
            transition_status,
            "evaluate_transition",
            side_effect=add_history_after_second_evaluation,
        ):
            result = transition_status.apply_transition(
                self.project,
                "STORY",
                "USER_APPROVED",
                expected_project_sha256=hashlib.sha256(before_project).hexdigest(),
            )
        self.assertFalse(result.get("applied"), result)
        self.assertEqual(before_project, project_path.read_bytes())

    def test_finish_authority_is_delivery_record_and_requires_picture_locked_timeline(self) -> None:
        timeline_path, _ = self._write_finish_fixture()

        from transition_status import evaluate_transition

        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            result = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertTrue(result["allowed"], result)

        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"].remove("APR_EDIT_0001")
        write_json(project_path, project)
        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            missing_edit = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertFalse(missing_edit["allowed"], missing_edit)
        self.assertTrue(
            any(
                "edit" in item["message"].casefold()
                and "active" in item["message"].casefold()
                for item in missing_edit["errors"]
            ),
            missing_edit,
        )

        project["active_approval_ids"].append("APR_EDIT_0001")
        write_json(project_path, project)
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        timeline["lock_status"] = "UNLOCKED"
        write_json(timeline_path, timeline)
        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            stale_edit = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertFalse(stale_edit["allowed"], stale_edit)
        self.assertIn(
            "E_APPROVAL_HASH_MISMATCH",
            {item["code"] for item in stale_edit["errors"]},
        )
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in stale_edit["errors"]})

    def test_finish_v1_delivery_must_remain_at_the_root_seed_path(self) -> None:
        _, root_delivery = self._write_finish_fixture()
        misplaced = (
            self.project
            / "08_delivery"
            / "records"
            / "final_delivery"
            / "v001"
            / "delivery.json"
        )
        payload = json.loads(root_delivery.read_text(encoding="utf-8"))
        write_json(misplaced, payload)
        root_delivery.unlink()
        digest = hashlib.sha256(misplaced.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_finish.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["subject_sha256"] = digest
        approval["evidence"][0] = {
            "path": "08_delivery/records/final_delivery/v001/delivery.json",
            "sha256": digest,
            "verified_claim": "Misplaced v1 delivery",
        }
        write_json(approval_path, approval)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["delivery_record"] = (
            "08_delivery/records/final_delivery/v001/delivery.json"
        )
        write_json(project_path, project)

        from transition_status import evaluate_transition

        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            result = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertTrue(any("version" in item["message"].casefold() for item in result["errors"]), result)

    def test_finish_v2_requires_a_valid_immediate_predecessor_contract(self) -> None:
        self._write_finish_fixture()
        v2_path = self._promote_finish_delivery_to_v2()

        from transition_status import evaluate_transition

        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            valid = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertTrue(valid["allowed"], valid)

        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
        v2["supersedes_delivery"]["sha256"] = "0" * 64
        write_json(v2_path, v2)
        v2_hash = hashlib.sha256(v2_path.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_finish_v002.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["subject_sha256"] = v2_hash
        approval["evidence"][0]["sha256"] = v2_hash
        write_json(approval_path, approval)
        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            invalid = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertFalse(invalid["allowed"], invalid)
        self.assertTrue(
            any("predecessor" in item["message"].casefold() for item in invalid["errors"]),
            invalid,
        )

    def test_singular_json_approval_subject_id_must_match_the_current_record(self) -> None:
        self._write_finish_fixture()
        approval_path = self.project / "09_approvals" / "approval_edit.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["subject_id"] = "unrelated_timeline"
        write_json(approval_path, approval)

        from transition_status import evaluate_transition

        with patch("verify_lineage.verify_lineage", return_value={"ok": True, "errors": []}):
            result = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertFalse(result["allowed"], result)
        self.assertTrue(
            any("timeline_id" in item["message"] for item in result["errors"]),
            result,
        )

    def test_superseding_a_gate_invalidates_downstream_state_and_can_restart(self) -> None:
        self.gates["STORY"] = "USER_APPROVED"
        storyboard = self.project / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard,
            {
                "project_id": "take-me",
                "storyboard_id": "storyboard",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
            },
        )
        self.gates["STORYBOARD"] = "USER_APPROVED"
        self._write_approval(
            "STORYBOARD",
            hashlib.sha256(storyboard.read_bytes()).hexdigest(),
            evidence_path="02_storyboard/storyboard.json",
        )
        visual_bible = self.project / "03_lookdev" / "VISUAL_BIBLE.md"
        visual_bible.parent.mkdir(parents=True)
        visual_bible.write_bytes(b"approved-lookdev")
        self.gates["LOOKDEV"] = "USER_APPROVED"
        self._write_approval(
            "LOOKDEV",
            hashlib.sha256(visual_bible.read_bytes()).hexdigest(),
            evidence_path="03_lookdev/VISUAL_BIBLE.md",
        )
        self.gates["ASSET_LOCK"] = "INTERNAL_REVIEW"
        self._write_project()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update(
            {
                "project_status": "ACTIVE",
                "review_status": "INTERNAL_REVIEW",
                "current_stage": "ASSET_LOCK",
                "active_approval_ids": [
                    "APR_STORY_0001",
                    "APR_STORYBOARD_0001",
                    "APR_LOOKDEV_0001",
                ],
            }
        )
        write_json(project_path, project)

        from transition_status import apply_transition

        before = hashlib.sha256(project_path.read_bytes()).hexdigest()
        superseded = apply_transition(
            self.project,
            "STORYBOARD",
            "SUPERSEDED",
            expected_project_sha256=before,
        )
        self.assertTrue(superseded.get("applied"), superseded)
        updated = json.loads(project_path.read_text(encoding="utf-8"))
        self.assertEqual("USER_APPROVED", updated["stage_gates"]["STORY"])
        self.assertEqual("SUPERSEDED", updated["stage_gates"]["STORYBOARD"])
        for gate in list(self.gates)[2:]:
            self.assertEqual("DRAFT", updated["stage_gates"][gate], gate)
        self.assertEqual(["APR_STORY_0001"], updated["active_approval_ids"])
        self.assertEqual("STORYBOARD", updated["current_stage"])
        self.assertEqual("ACTIVE", updated["project_status"])
        self.assertNotEqual("USER_APPROVED", updated["review_status"])

        restart_hash = hashlib.sha256(project_path.read_bytes()).hexdigest()
        restarted = apply_transition(
            self.project,
            "STORYBOARD",
            "DRAFT",
            expected_project_sha256=restart_hash,
        )
        self.assertTrue(restarted.get("applied"), restarted)
        self.assertEqual("DRAFT", json.loads(project_path.read_text(encoding="utf-8"))["stage_gates"]["STORYBOARD"])

    def test_remote_generation_accepts_only_a_bound_offline_evidence_package(self) -> None:
        output = self.project / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "out.mov"
        package = self.project / "99_logs" / "remote" / "job-1.json"
        output.parent.mkdir(parents=True)
        package.parent.mkdir(parents=True)
        output.write_bytes(b"generated-output")
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        write_json(
            package,
            {
                "verification_scope": "OFFLINE_RECORD_CONSISTENCY",
                "provider": "Higgsfield",
                "project_id": "project-1",
                "job_id": "job-1",
                "model_name": "Seedance",
                "output_sha256": output_hash,
            },
        )
        package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
        take = {
            "project_id": "take-me",
            "take_id": "S01_SH010_T01",
            "shot_id": "S01_SH010",
            "coverage_requirement_ids": ["COV_REMOTE"],
            "execution_origin": "REMOTE_GENERATION",
            "output_file": str(output.relative_to(self.project)).replace("\\", "/"),
            "output_sha256": output_hash,
            "input_hashes": [{"path": str(package.relative_to(self.project)).replace("\\", "/"), "sha256": package_hash}],
            "model": {"provider": "Higgsfield", "name": "Seedance", "version": "2", "verified": True},
            "diagnosis": {"verdict": "PASS", "first_failure": None, "what_held": ["motion"]},
            "remote_job_id": "job-1",
            "remote": {
                "provider": "Higgsfield",
                "project_id": "project-1",
                "job_id": "job-1",
                "verified": True,
                "evidence": [
                    {
                        "path": str(package.relative_to(self.project)).replace("\\", "/"),
                        "sha256": package_hash,
                        "verified_claim": "offline record consistency only",
                    }
                ],
            },
        }

        from transition_status import _check_video_proof

        take_path = output.parent / "take.json"
        write_json(take_path, take)
        self._write_approval(
            "RAW_VIDEO",
            output_hash,
            evidence_path=str(output.relative_to(self.project)).replace("\\", "/"),
            subject_id="S01_SH010_T01",
        )
        approval_path = self.project / "09_approvals" / "approval_raw_video.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        errors: list[dict] = []
        _check_video_proof(
            self.project,
            {"project_id": "take-me"},
            [(take, take_path), (approval, approval_path)],
            errors,
        )
        self.assertEqual([], errors)

        payload = json.loads(package.read_text(encoding="utf-8"))
        payload["job_id"] = "fabricated-other-job"
        write_json(package, payload)
        take["remote"]["evidence"][0]["sha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
        inconsistent: list[dict] = []
        _check_video_proof(
            self.project,
            {"project_id": "take-me"},
            [(take, take_path), (approval, approval_path)],
            inconsistent,
        )
        self.assertIn("E_REMOTE_PROOF_MISSING", {item["code"] for item in inconsistent})

    def test_dependency_cas_tracks_storyboard_panel_images_and_all_immutable_history(self) -> None:
        from transition_status import _dependency_snapshot, _dependency_snapshot_matches

        panel = self.project / "02_storyboard" / "panels" / "S01_P001.png"
        panel.parent.mkdir(parents=True, exist_ok=True)
        panel.write_bytes(b"visible-panel")
        write_json(
            self.project / "02_storyboard" / "storyboard.json",
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "scenes": [
                    {
                        "scene_id": "S01",
                        "order": 1,
                        "panels": [
                            {
                                "panel_id": "S01_P001",
                                "order": 1,
                                "image_file": "02_storyboard/panels/S01_P001.png",
                                "image_sha256": hashlib.sha256(panel.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ],
            },
        )
        historical = (
            self.project
            / "07_edit"
            / "records"
            / "main_timeline"
            / "v002"
            / "timeline.json"
        )
        write_json(
            historical,
            {
                "schema_id": "cinema-studio-pipeline/timeline@2.0.0",
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 2,
            },
        )
        legacy_fixed_archive = (
            self.project
            / "01_story"
            / "history"
            / "story-contract"
            / "v001"
            / "STORY_CONTRACT.md"
        )
        legacy_fixed_archive.parent.mkdir(parents=True, exist_ok=True)
        legacy_fixed_archive.write_bytes(b"preserved-legacy-story")
        shot_archive = (
            self.project
            / "05_shots"
            / "S01_SH001"
            / "history"
            / "v001"
            / "shot.json"
        )
        shot_archive.parent.mkdir(parents=True, exist_ok=True)
        shot_archive.write_bytes(b"preserved-shot-candidate")
        source_archive = (
            self.project
            / "06_source_library"
            / "history"
            / "source_main"
            / "v001"
            / "source_manifest.json"
        )
        source_archive.parent.mkdir(parents=True, exist_ok=True)
        source_archive.write_bytes(b"preserved-source-library-candidate")
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        errors: list[dict] = []

        snapshot = _dependency_snapshot(self.project, project, [], errors)
        paths = {item["path"] for item in snapshot["files"]}

        self.assertEqual([], errors)
        self.assertIn("02_storyboard/panels/S01_P001.png", paths)
        self.assertIn("07_edit/records/main_timeline/v002/timeline.json", paths)
        self.assertIn(
            "01_story/history/story-contract/v001/STORY_CONTRACT.md",
            paths,
        )
        self.assertIn("05_shots/S01_SH001/history/v001/shot.json", paths)
        self.assertIn(
            "06_source_library/history/source_main/v001/source_manifest.json",
            paths,
        )

        legacy_fixed_archive.write_bytes(b"mutated-after-preflight")
        self.assertFalse(_dependency_snapshot_matches(self.project, snapshot))

    def test_collection_transition_requires_exact_storyboard_asset_plan_closure(self) -> None:
        from transition_status import _read_records, _validate_collection_gate

        self._write_approved_asset("hero", "APR_ASSET_LOCK_0001")
        hero_path = self.project / "04_assets" / "records" / "hero" / "asset.json"
        hero = json.loads(hero_path.read_text(encoding="utf-8"))
        hero["kind"] = "LOCATION"
        hero["state"] = {"label": "damaged"}
        write_json(hero_path, hero)
        write_json(
            self.project / "02_storyboard" / "storyboard.json",
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "asset_plan": [
                    {"asset_id": "hero", "kind": "CHARACTER", "state_label": "default"},
                    {"asset_id": "moon", "kind": "LOCATION", "state_label": "night"},
                ],
                "shot_plan": [],
            },
        )
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        records = _read_records(self.project, project)
        errors: list[dict] = []

        _validate_collection_gate(
            self.project,
            project,
            records,
            "ASSET_LOCK",
            set(),
            errors,
            require_active=False,
        )

        self.assertTrue(
            any("planned asset" in item["message"].lower() and "moon" in item["message"] for item in errors),
            errors,
        )
        self.assertTrue(
            any(
                item["code"] == "ASSET_PLAN_MISMATCH"
                and "hero" in item["message"]
                for item in errors
            ),
            errors,
        )

    def test_raw_video_transition_enforces_storyboard_coverage_minimums(self) -> None:
        from transition_status import _read_records, _validate_collection_gate

        write_json(
            self.project / "02_storyboard" / "storyboard.json",
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "shot_plan": [
                    {
                        "shot_id": "S01_SH001",
                        "coverage_requirements": [
                            {
                                "coverage_id": "COV_PRIMARY",
                                "kind": "PRIMARY_ACTION",
                                "description": "Primary action",
                                "minimum_approved_takes": 2,
                            }
                        ],
                    }
                ],
            },
        )
        output = self.project / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "out.mov"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"approved-take")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        write_json(
            output.parent / "take.json",
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
                "take_id": "S01_SH001_T01",
                "coverage_requirement_ids": ["COV_PRIMARY"],
                "review_status": "USER_APPROVED",
                "approval_id": "APR_RAW_VIDEO_0001",
                "output_file": output.relative_to(self.project).as_posix(),
                "output_sha256": digest,
            },
        )
        approval_path = self.project / "09_approvals" / "APR_RAW_VIDEO_0001.json"
        write_json(
            approval_path,
            {
                "project_id": "take-me",
                "approval_id": "APR_RAW_VIDEO_0001",
                "subject_type": "TAKE",
                "subject_id": "S01_SH001_T01",
                "subject_sha256": digest,
                "gate": "RAW_VIDEO",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "user_evidence_reference": "visible-take",
                "evidence": [
                    {
                        "path": output.relative_to(self.project).as_posix(),
                        "sha256": digest,
                    }
                ],
            },
        )
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        records = _read_records(self.project, project)
        errors: list[dict] = []

        _validate_collection_gate(
            self.project,
            project,
            records,
            "RAW_VIDEO",
            set(),
            errors,
            require_active=False,
        )

        self.assertTrue(
            any("COV_PRIMARY" in item["message"] and "requires 2" in item["message"] for item in errors),
            errors,
        )

    def test_edit_transition_requires_bidirectional_timeline_approval_replacement_links(self) -> None:
        from transition_status import _check_gate_authority

        timeline_v1_path = self.project / "07_edit" / "timeline.json"
        timeline_v1 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "supersedes_timeline": None,
            "review_status": "USER_APPROVED",
            "lock_status": "PICTURE_LOCKED",
            "approval_id": "APR_EDIT_0001",
        }
        write_json(timeline_v1_path, timeline_v1)
        timeline_v1_hash = hashlib.sha256(timeline_v1_path.read_bytes()).hexdigest()
        timeline_v2_path = self.project / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v2 = {
            **timeline_v1,
            "version": 2,
            "approval_id": "APR_EDIT_0002",
            "supersedes_timeline": {
                "timeline_id": "main_timeline",
                "version": 1,
                "path": "07_edit/timeline.json",
                "sha256": timeline_v1_hash,
                "approval_id": "APR_EDIT_0001",
            },
        }
        write_json(timeline_v2_path, timeline_v2)
        timeline_v2_hash = hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest()
        old_approval_path = self.project / "09_approvals" / "approval_edit_v001.json"
        new_approval_path = self.project / "09_approvals" / "approval_edit_v002.json"
        old_approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0001",
            "gate": "EDIT",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": timeline_v1_hash,
            "review_status": "USER_APPROVED",
            "supersedes_approval_id": None,
            "superseded_by_approval_id": None,
        }
        new_approval = {
            **old_approval,
            "approval_id": "APR_EDIT_0002",
            "subject_sha256": timeline_v2_hash,
            "evidence": [
                {
                    "path": timeline_v2_path.relative_to(self.project).as_posix(),
                    "sha256": timeline_v2_hash,
                }
            ],
        }
        write_json(old_approval_path, old_approval)
        write_json(new_approval_path, new_approval)
        project = {
            "project_id": "take-me",
            "authority_files": {
                "timeline": timeline_v2_path.relative_to(self.project).as_posix(),
            },
        }
        records = [(old_approval, old_approval_path), (new_approval, new_approval_path)]
        errors: list[dict] = []

        _check_gate_authority(
            self.project,
            project,
            records,
            (new_approval, new_approval_path),
            "EDIT",
            errors,
        )

        self.assertTrue(
            any(
                item["code"] == "E_APPROVAL_HASH_MISMATCH"
                and "predecessor" in item["message"].lower()
                for item in errors
            ),
            errors,
        )

        old_approval["superseded_by_approval_id"] = "APR_EDIT_0002"
        new_approval["supersedes_approval_id"] = "APR_EDIT_0001"
        linked_errors: list[dict] = []
        _check_gate_authority(
            self.project,
            project,
            records,
            (new_approval, new_approval_path),
            "EDIT",
            linked_errors,
        )
        self.assertFalse(
            any("predecessor" in item["message"].lower() for item in linked_errors),
            linked_errors,
        )

    def test_user_review_required_requires_exact_current_central_review_package(self) -> None:
        from transition_status import evaluate_transition

        self.gates["STORY"] = "DRAFT"
        self._write_project()
        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval_path.unlink()

        missing = evaluate_transition(self.project, "STORY", "USER_REVIEW_REQUIRED")
        self.assertFalse(missing["allowed"], missing)
        self.assertTrue(
            any(item["code"] == "E_UNAPPROVED_INPUT" for item in missing["errors"]),
            missing,
        )

        write_json(
            approval_path,
            {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "approval_id": "APR_STORY_0002",
                "subject_type": "STORY",
                "subject_id": "story-contract",
                "subject_sha256": self.hash,
                "gate": "STORY",
                "review_status": "USER_REVIEW_REQUIRED",
                "requested_by": "project-owner",
                "requested_at": "2026-08-12T00:00:00Z",
                "evidence": [
                    {
                        "path": "01_story/STORY_CONTRACT.md",
                        "sha256": self.hash,
                        "verified_claim": "Current story candidate",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )
        prepared = evaluate_transition(self.project, "STORY", "USER_REVIEW_REQUIRED")
        self.assertTrue(prepared["allowed"], prepared)
        self.assertEqual(prepared["selected_approval_ids"], ["APR_STORY_0002"])

        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval.update(
            {
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "project-owner",
                "decided_at": "2026-08-12T01:00:00Z",
                "user_evidence_reference": "chat-already-approved",
            }
        )
        write_json(approval_path, approval)
        already_approved = evaluate_transition(
            self.project, "STORY", "USER_REVIEW_REQUIRED"
        )
        self.assertFalse(already_approved["allowed"], already_approved)
        self.assertIn(
            "E_UNAPPROVED_INPUT",
            {item["code"] for item in already_approved["errors"]},
        )

    def test_rejected_transition_requires_an_exact_terminal_central_decision(self) -> None:
        from transition_status import apply_transition, evaluate_transition

        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        expected = hashlib.sha256(before).hexdigest()

        # A pending gate plus an old USER_APPROVED record is not a rejection decision.
        denied = apply_transition(
            self.project,
            "STORY",
            "REJECTED",
            expected_project_sha256=expected,
        )
        self.assertFalse(denied["allowed"], denied)
        self.assertFalse(denied["applied"], denied)
        self.assertEqual(before, project_path.read_bytes())

        approval_path = self.project / "09_approvals" / "approval_story.json"
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["review_status"] = "REJECTED"
        approval["decision_notes"] = "Story needs revision"
        approval.pop("user_evidence_reference", None)
        write_json(approval_path, approval)

        rejected = evaluate_transition(self.project, "STORY", "REJECTED")
        self.assertTrue(rejected["allowed"], rejected)
        self.assertEqual(["APR_STORY_0001"], rejected["selected_approval_ids"])

    def test_collection_gate_cannot_be_rejected_as_an_aggregate(self) -> None:
        from transition_status import evaluate_transition

        self.gates["STORY"] = "USER_APPROVED"
        self.gates["STORYBOARD"] = "USER_APPROVED"
        self.gates["LOOKDEV"] = "USER_APPROVED"
        self.gates["ASSET_LOCK"] = "USER_REVIEW_REQUIRED"
        self._write_project()

        result = evaluate_transition(self.project, "ASSET_LOCK", "REJECTED")

        self.assertFalse(result["allowed"], result)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_edit_authority_uses_central_approval_without_self_status_fields(self) -> None:
        from transition_status import _check_gate_authority

        timeline_path = self.project / "07_edit" / "timeline.json"
        write_json(
            timeline_path,
            {
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 1,
                "supersedes_timeline": None,
                "lock_status": "PICTURE_LOCKED",
            },
        )
        digest = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_edit.json"
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0001",
            "gate": "EDIT",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": digest,
            "review_status": "USER_APPROVED",
            "evidence": [
                {
                    "path": "07_edit/timeline.json",
                    "sha256": digest,
                    "verified_claim": "Current picture lock",
                }
            ],
            "supersedes_approval_id": None,
            "superseded_by_approval_id": None,
        }
        project = {
            "project_id": "take-me",
            "authority_files": {"timeline": "07_edit/timeline.json"},
        }
        errors: list[dict] = []
        _check_gate_authority(
            self.project,
            project,
            [(approval, approval_path)],
            (approval, approval_path),
            "EDIT",
            errors,
        )

        self.assertEqual(errors, [])

    def test_shot_collection_uses_central_decision_without_self_status_fields(self) -> None:
        from transition_status import _read_records, _validate_collection_gate

        write_json(
            self.project / "02_storyboard" / "storyboard.json",
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "asset_plan": [],
                "shot_plan": [{"shot_id": "S01_SH001"}],
            },
        )
        shot_path = self.project / "05_shots" / "S01_SH001" / "shot.json"
        write_json(
            shot_path,
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
            },
        )
        digest = hashlib.sha256(shot_path.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_shot.json"
        write_json(
            approval_path,
            {
                "project_id": "take-me",
                "approval_id": "APR_SHOT_STILL_0001",
                "gate": "SHOT_STILL",
                "subject_type": "SHOT_STILL",
                "subject_id": "S01_SH001",
                "subject_sha256": digest,
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "fixture-user",
                "user_evidence_reference": "visible-shot",
                "evidence": [
                    {
                        "path": "05_shots/S01_SH001/shot.json",
                        "sha256": digest,
                        "verified_claim": "Current shot card",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        records = _read_records(self.project, project)
        errors: list[dict] = []
        selected = _validate_collection_gate(
            self.project,
            project,
            records,
            "SHOT_STILL",
            set(),
            errors,
            require_active=False,
        )

        self.assertEqual(errors, [])
        self.assertEqual([item[0]["approval_id"] for item in selected], ["APR_SHOT_STILL_0001"])

    def test_finish_uses_central_edit_and_delivery_approvals_without_self_status_fields(self) -> None:
        from transition_status import evaluate_transition

        timeline_path, delivery_path = self._write_finish_fixture()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        timeline.pop("review_status", None)
        timeline.pop("approval_id", None)
        write_json(timeline_path, timeline)
        timeline_hash = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        edit_approval_path = self.project / "09_approvals" / "approval_edit.json"
        edit_approval = json.loads(edit_approval_path.read_text(encoding="utf-8"))
        edit_approval["subject_sha256"] = timeline_hash
        edit_approval["evidence"][0]["sha256"] = timeline_hash
        write_json(edit_approval_path, edit_approval)

        delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
        delivery.pop("review_status", None)
        delivery.pop("approval_id", None)
        delivery["source_timeline"]["sha256"] = timeline_hash
        delivery["derivation"]["input_hashes"][0]["sha256"] = timeline_hash
        write_json(delivery_path, delivery)
        delivery_hash = hashlib.sha256(delivery_path.read_bytes()).hexdigest()
        finish_approval_path = self.project / "09_approvals" / "approval_finish.json"
        finish_approval = json.loads(finish_approval_path.read_text(encoding="utf-8"))
        finish_approval["subject_sha256"] = delivery_hash
        finish_approval["evidence"][0]["sha256"] = delivery_hash
        write_json(finish_approval_path, finish_approval)

        result = evaluate_transition(self.project, "FINISH", "USER_APPROVED")
        self.assertTrue(result["allowed"], result)

    def test_source_library_uses_exact_central_approval_without_self_status_fields(self) -> None:
        from transition_status import _check_source_library, _read_records

        output = self.project / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "out.mov"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"approved-source")
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        write_json(
            output.parent / "take.json",
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
                "take_id": "S01_SH001_T01",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_RAW_VIDEO_0001",
                "source_status": "SOURCE_APPROVED",
                "output_file": output.relative_to(self.project).as_posix(),
                "output_sha256": output_hash,
            },
        )
        write_json(
            self.project / "09_approvals" / "approval_take.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_RAW_VIDEO_0001",
                "gate": "RAW_VIDEO",
                "subject_type": "TAKE",
                "subject_id": "S01_SH001_T01",
                "subject_sha256": output_hash,
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "fixture-user",
                "user_evidence_reference": "visible-take",
                "evidence": [
                    {
                        "path": output.relative_to(self.project).as_posix(),
                        "sha256": output_hash,
                        "verified_claim": "Approved source take",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )
        manifest_path = self.project / "06_source_library" / "source_manifest.json"
        write_json(
            manifest_path,
            {
                "project_id": "take-me",
                "library_id": "source_library",
                "lock_status": "SOURCE_LOCKED",
                "sources": [
                    {
                        "source_id": "SRC_001",
                        "take_id": "S01_SH001_T01",
                        "path": output.relative_to(self.project).as_posix(),
                        "sha256": output_hash,
                        "source_status": "SOURCE_APPROVED",
                    }
                ],
            },
        )
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        approval_path = self.project / "09_approvals" / "approval_source.json"
        write_json(
            approval_path,
            {
                "project_id": "take-me",
                "approval_id": "APR_SOURCE_LIBRARY_0001",
                "gate": "SOURCE_LIBRARY",
                "subject_type": "SOURCE_LIBRARY",
                "subject_id": "source_library",
                "subject_sha256": manifest_hash,
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "fixture-user",
                "user_evidence_reference": "visible-source-lock",
                "evidence": [
                    {
                        "path": "06_source_library/source_manifest.json",
                        "sha256": manifest_hash,
                        "verified_claim": "Current locked source library",
                    }
                ],
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
            },
        )
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8"))
        project["authority_files"] = {
            "source_manifest": "06_source_library/source_manifest.json"
        }
        records = _read_records(self.project, project)
        errors: list[dict] = []
        _check_source_library(self.project, project, records, errors)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
