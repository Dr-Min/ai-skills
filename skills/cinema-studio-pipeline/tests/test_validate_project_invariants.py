import json
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ValidateProjectInvariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.schemas = self.root / "empty-schemas"
        self.schemas.mkdir()
        self.gates = {
            gate: "USER_APPROVED"
            for gate in (
                "STORY", "STORYBOARD", "LOOKDEV", "ASSET_LOCK", "SHOT_STILL",
                "RAW_VIDEO", "SOURCE_LIBRARY", "EDIT", "FINISH",
            )
        }
        write_json(
            self.root / "project.json",
            {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "project_status": "COMPLETED",
                "current_stage": "COMPLETE",
                "review_status": "USER_APPROVED",
                "stage_gates": self.gates,
                "active_approval_ids": [],
                "authority_files": {
                    "asset_records_root": "04_assets/records",
                    "source_manifest": "06_source_library/source_manifest.json",
                    "timeline": "07_edit/timeline.json",
                },
                "paths": {"shots": "05_shots", "approvals": "09_approvals"},
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rejects_complete_project_without_active_approvals_and_escaped_paths(self) -> None:
        write_json(
            self.root / "04_assets" / "records" / "woman" / "asset.json",
            {
                "asset_id": "woman",
                "review_status": "INTERNAL_REVIEW",
                "files": {"immutable_master": {"path": "../outside.png", "sha256": None}},
                "lineage": {"derivation": "IMPORTED", "parent_asset_id": None, "input_hashes": [], "output_sha256": None},
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_STAGE_PREREQ", codes)
        self.assertIn("PATH_ESCAPE", codes)

    def test_rejects_prefix_mismatches_duplicate_sources_bad_timeline_and_unreviewed_derivatives(self) -> None:
        write_json(
            self.root / "05_shots" / "S01_SH010" / "shot.json",
            {"shot_id": "S01_SH010", "scene_id": "S02", "review_status": "DRAFT", "active_assets": []},
        )
        write_json(
            self.root / "05_shots" / "S01_SH010" / "takes" / "S01_SH010_T01" / "take.json",
            {
                "take_id": "S01_SH010_T01",
                "shot_id": "S01_SH010",
                "review_status": "INTERNAL_REVIEW",
                "lineage": {"derivation": "UPSCALE", "parent_take_id": None, "source_asset_ids": [], "source_take_ids": []},
                "diagnosis": {"verdict": "NOT_REVIEWED"},
            },
        )
        write_json(
            self.root / "06_source_library" / "source_manifest.json",
            {
                "sources": [
                    {"source_id": "SRC_A", "take_id": "S01_SH010_T01", "path": "a.mp4", "sha256": "a" * 64, "source_status": "SOURCE_APPROVED"},
                    {"source_id": "SRC_A", "take_id": "S01_SH010_T01", "path": "b.mp4", "sha256": "b" * 64, "source_status": "SOURCE_APPROVED"},
                ]
            },
        )
        write_json(
            self.root / "07_edit" / "timeline.json",
            {
                "tracks": [{"track_id": "TRK_V1"}],
                "clips": [{"clip_id": "CLIP_A", "track_id": "TRK_BAD", "source_id": "SRC_MISSING", "source_in_frame": 10, "source_out_frame": 5, "timeline_in_frame": 0, "timeline_out_frame": 0}],
                "events": [],
                "lock_status": "PICTURE_LOCKED",
            },
        )
        write_json(
            self.root / "02_storyboard" / "storyboard.json",
            {
                "panels": [
                    {"panel_id": "S01_P001", "order": 1, "active_assets": []},
                    {"panel_id": "S01_P001", "order": 1, "active_assets": []},
                ]
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["storyboard"] = "02_storyboard/storyboard.json"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        codes = {item["code"] for item in result["errors"]}
        for expected in (
            "ID_PREFIX_MISMATCH",
            "LINEAGE_PARENT_MISSING",
            "DIAGNOSIS_NOT_REVIEWED",
            "DUPLICATE_SOURCE_ID",
            "UNKNOWN_TRACK",
            "UNKNOWN_SOURCE",
            "INVALID_FRAME_RANGE",
            "E_STAGE_PREREQ",
            "DUPLICATE_PANEL_ID",
        ):
            self.assertIn(expected, codes)

    def test_schema_invalid_unhashable_timeline_members_fail_closed(self) -> None:
        write_json(
            self.root / "07_edit" / "timeline.json",
            {
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "tracks": [{"track_id": {"bad": "id"}, "order": [1]}],
                "clips": [
                    {
                        "clip_id": {"bad": "clip"},
                        "track_id": ["TRK_V1"],
                        "source_id": {"bad": "source"},
                        "linked_event_ids": [["EVT_A"]],
                    }
                ],
                "events": [{"event_id": {"bad": "event"}}],
                "lock_status": "UNLOCKED",
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)

        self.assertFalse(result["ok"], result)
        self.assertIn("INVALID_RECORD", {item["code"] for item in result["errors"]})

    def test_semantic_phase_wrapper_never_exposes_untrusted_shape_exceptions(self) -> None:
        from validate_project import _run_semantic_check

        errors: list[dict] = []

        def malformed_phase() -> None:
            raise RuntimeError("unexpected malformed shape")

        _run_semantic_check(errors, malformed_phase)

        self.assertEqual("VALIDATION_RUNTIME_ERROR", errors[0]["code"])
        self.assertIn("RuntimeError", errors[0]["message"])

    def test_v2_declared_schema_snapshot_is_fail_closed_when_missing(self) -> None:
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["paths"]["schemas"] = "00_schemas"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root)
        self.assertIn("SCHEMA_SNAPSHOT_MISSING", {item["code"] for item in result["errors"]})
        self.assertEqual("project_snapshot", result["schema_source"])

    def test_never_hashes_approval_evidence_outside_the_project(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.bin"
        outside.write_bytes(b"outside")
        write_json(
            self.root / "09_approvals" / "APR_STORY_0001.json",
            {
                "approval_id": "APR_STORY_0001",
                "subject_type": "STORY",
                "subject_id": "story-contract",
                "subject_sha256": "a" * 64,
                "gate": "STORY",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "user_evidence_reference": "user-click",
                "evidence": [{"path": "../" + outside.name, "sha256": "a" * 64}],
            },
        )

        from validate_project import sha256_file as real_sha256, validate_project

        def guarded_hash(path: Path) -> str:
            path.resolve().relative_to(self.root.resolve())
            return real_sha256(path)

        try:
            with patch("validate_project.sha256_file", side_effect=guarded_hash):
                result = validate_project(self.root, schema_dir=self.schemas)
        finally:
            outside.unlink(missing_ok=True)
        self.assertIn("PATH_ESCAPE", {item["code"] for item in result["errors"]})

    def test_subject_type_gate_mapping_is_enforced_without_schema_engine(self) -> None:
        write_json(
            self.root / "09_approvals" / "APR_BAD_0001.json",
            {
                "approval_id": "APR_BAD_0001",
                "subject_type": "TAKE",
                "subject_id": "S01_SH001_T01",
                "subject_sha256": None,
                "gate": "SOURCE_LIBRARY",
                "review_status": "DRAFT",
                "evidence": [],
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("APPROVAL_GATE_MISMATCH", {item["code"] for item in result["errors"]})

    def test_completion_requires_one_active_approval_for_every_gate(self) -> None:
        evidence = self.root / "01_story" / "STORY_CONTRACT.md"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("approved", encoding="utf-8")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        approval_ids: list[str] = []
        for number in range(1, 10):
            approval_id = f"APR_STORY_{number:04d}"
            approval_ids.append(approval_id)
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "approval_id": approval_id,
                    "subject_type": "STORY",
                    "subject_id": "story-contract",
                    "subject_sha256": digest,
                    "gate": "STORY",
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "decided_by": "owner",
                    "decided_at": "2026-08-11T00:00:00Z",
                    "user_evidence_reference": "user-click",
                    "evidence": [{"path": "01_story/STORY_CONTRACT.md", "sha256": digest}],
                },
            )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = approval_ids
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_story_approval_hash_must_match_current_authority_target(self) -> None:
        story = self.root / "01_story" / "STORY_CONTRACT.md"
        stale = self.root / "01_story" / "stale-copy.md"
        story.parent.mkdir(parents=True)
        story.write_text("current story", encoding="utf-8")
        stale.write_text("older approved story", encoding="utf-8")
        stale_hash = hashlib.sha256(stale.read_bytes()).hexdigest()
        write_json(
            self.root / "09_approvals" / "APR_STORY_0001.json",
            {
                "approval_id": "APR_STORY_0001",
                "subject_type": "STORY",
                "subject_id": "story-contract",
                "subject_sha256": stale_hash,
                "gate": "STORY",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "owner",
                "decided_at": "2026-08-11T00:00:00Z",
                "user_evidence_reference": "user-click",
                "evidence": [{"path": "01_story/stale-copy.md", "sha256": stale_hash}],
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["story_contract"] = "01_story/STORY_CONTRACT.md"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})

    def test_verified_remote_evidence_hash_is_checked_against_actual_bytes(self) -> None:
        proof = self.root / "99_logs" / "remote-proof.json"
        proof.parent.mkdir(parents=True)
        proof.write_text("real proof", encoding="utf-8")
        write_json(
            self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.json",
            {
                "take_id": "S01_SH001_T01",
                "shot_id": "S01_SH001",
                "review_status": "USER_APPROVED",
                "source_status": "SOURCE_APPROVED",
                "approval_id": "APR_TAKE_0001",
                "execution_origin": "REMOTE_GENERATION",
                "output_file": "05_shots/S01_SH001/takes/S01_SH001_T01/out.mov",
                "output_sha256": "a" * 64,
                "model": {"name": "Seedance", "verified": True},
                "remote": {
                    "verified": True,
                    "job_id": "job-1",
                    "project_id": "project-1",
                    "verified_at": "2026-08-11T00:00:00Z",
                    "evidence": [{"path": "99_logs/remote-proof.json", "sha256": "b" * 64}],
                },
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_REMOTE_PROOF_MISSING", {item["code"] for item in result["errors"]})
        self.assertFalse(result["remote_truth_verified"])
        self.assertEqual("OFFLINE_RECORD_CONSISTENCY", result["verification_scope"])

    def test_local_processing_input_hash_is_checked_against_actual_bytes(self) -> None:
        source = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T00" / "raw.mov"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"actual input")
        output = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "out.mov"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"local output")
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        take_path = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.json"
        write_json(
            take_path,
            {
                "project_id": "take-me",
                "take_id": "S01_SH001_T01",
                "shot_id": "S01_SH001",
                "coverage_requirement_ids": ["COV_LOCAL"],
                "execution_origin": "LOCAL_PROCESSING",
                "output_file": "05_shots/S01_SH001/takes/S01_SH001_T01/out.mov",
                "output_sha256": output_hash,
                "model": {"name": "ffmpeg", "version": "8", "verified": True},
                "generation_parameters": {"codec": "prores"},
                "remote_job_id": None,
                "remote_url": None,
                "remote": {"verified": False, "job_id": None},
                "input_hashes": [
                    {
                        "path": "05_shots/S01_SH001/takes/S01_SH001_T00/raw.mov",
                        "sha256": "b" * 64,
                    }
                ],
                "lineage": {"parent_take_id": "S01_SH001_T00", "derivation": "TRANSCODE"},
                "diagnosis": {"verdict": "PASS", "first_failure": None, "what_held": ["timing"]},
            },
        )
        write_json(
            self.root / "09_approvals" / "APR_TAKE_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_TAKE_0001",
                "subject_type": "TAKE",
                "subject_id": "S01_SH001_T01",
                "subject_sha256": output_hash,
                "gate": "RAW_VIDEO",
                "review_status": "USER_REVIEW_REQUIRED",
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
                "evidence": [
                    {
                        "path": "05_shots/S01_SH001/takes/S01_SH001_T01/out.mov",
                        "sha256": output_hash,
                        "verified_claim": "Candidate output bytes",
                    },
                    {
                        "path": "05_shots/S01_SH001/takes/S01_SH001_T01/take.json",
                        "sha256": hashlib.sha256(take_path.read_bytes()).hexdigest(),
                        "verified_claim": "Candidate take record",
                    },
                ],
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})

    def test_completion_rejects_generic_project_stage_approvals_reusing_one_hash(self) -> None:
        evidence = self.root / "01_story" / "STORY_CONTRACT.md"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("one artifact", encoding="utf-8")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        active: list[str] = []
        for index, gate in enumerate(self.gates, start=1):
            approval_id = f"APR_STAGE_{index:04d}"
            active.append(approval_id)
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "approval_id": approval_id,
                    "subject_type": "PROJECT_STAGE",
                    "subject_id": gate,
                    "subject_sha256": digest,
                    "gate": gate,
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "decided_by": "owner",
                    "decided_at": "2026-08-11T00:00:00Z",
                    "user_evidence_reference": "user-click",
                    "evidence": [{"path": "01_story/STORY_CONTRACT.md", "sha256": digest}],
                },
            )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["active_approval_ids"] = active
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_each_approved_gate_requires_its_active_concrete_approval_before_completion(self) -> None:
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update(
            {
                "project_status": "ACTIVE",
                "current_stage": "STORYBOARD",
                "review_status": "DRAFT",
                "stage_gates": {
                    gate: ("USER_APPROVED" if gate == "STORY" else "DRAFT")
                    for gate in self.gates
                },
                "active_approval_ids": [],
            }
        )
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_STAGE_PREREQ", {item["code"] for item in result["errors"]})

    def test_all_authority_records_must_match_the_project_id(self) -> None:
        wrong = "another-project"
        write_json(
            self.root / "04_assets" / "records" / "woman" / "asset.json",
            {"project_id": wrong, "asset_id": "woman", "review_status": "DRAFT"},
        )
        write_json(
            self.root / "05_shots" / "S01_SH001" / "shot.json",
            {"project_id": wrong, "scene_id": "S01", "shot_id": "S01_SH001", "review_status": "DRAFT"},
        )
        write_json(
            self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.json",
            {"project_id": wrong, "shot_id": "S01_SH001", "take_id": "S01_SH001_T01", "review_status": "DRAFT"},
        )
        write_json(
            self.root / "09_approvals" / "APR_STORY_0001.json",
            {"project_id": wrong, "approval_id": "APR_STORY_0001", "subject_type": "STORY", "gate": "STORY", "review_status": "DRAFT"},
        )
        write_json(
            self.root / "06_source_library" / "source_manifest.json",
            {"project_id": wrong, "library_id": "take-me-library", "sources": [{"project_id": wrong, "source_id": "SRC_001"}]},
        )
        write_json(
            self.root / "07_edit" / "timeline.json",
            {"project_id": wrong, "timeline_id": "take-me-main", "tracks": [], "clips": [], "events": []},
        )
        write_json(
            self.root / "02_storyboard" / "storyboard.json",
            {"project_id": wrong, "storyboard_id": "S01_SB001", "panels": []},
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["storyboard"] = "02_storyboard/storyboard.json"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        mismatches = [item for item in result["errors"] if item["code"] == "PROJECT_ID_MISMATCH"]
        self.assertGreaterEqual(len(mismatches), 7, result)

    def test_derived_take_input_must_bind_to_declared_parent_output(self) -> None:
        parent_output = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T00" / "raw.mov"
        child_output = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "processed.mov"
        unrelated = self.root / "05_shots" / "unrelated.mov"
        parent_output.parent.mkdir(parents=True)
        child_output.parent.mkdir(parents=True)
        parent_output.write_bytes(b"parent")
        child_output.write_bytes(b"child")
        unrelated.write_bytes(b"unrelated")
        parent_hash = hashlib.sha256(parent_output.read_bytes()).hexdigest()
        child_hash = hashlib.sha256(child_output.read_bytes()).hexdigest()
        unrelated_hash = hashlib.sha256(unrelated.read_bytes()).hexdigest()
        write_json(
            parent_output.parent / "take.json",
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
                "take_id": "S01_SH001_T00",
                "review_status": "DRAFT",
                "output_file": parent_output.relative_to(self.root).as_posix(),
                "output_sha256": parent_hash,
                "input_hashes": [],
                "lineage": {"parent_take_id": None, "source_take_ids": [], "source_asset_ids": [], "derivation": "GENERATED"},
            },
        )
        write_json(
            child_output.parent / "take.json",
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
                "take_id": "S01_SH001_T01",
                "review_status": "INTERNAL_REVIEW",
                "output_file": child_output.relative_to(self.root).as_posix(),
                "output_sha256": child_hash,
                "input_hashes": [{"path": unrelated.relative_to(self.root).as_posix(), "sha256": unrelated_hash}],
                "lineage": {"parent_take_id": "S01_SH001_T00", "source_take_ids": [], "source_asset_ids": [], "derivation": "TRANSCODE"},
                "diagnosis": {"verdict": "PASS"},
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_DERIVATIVE_AS_EDIT_BASE", {item["code"] for item in result["errors"]})

    def test_shot_structural_references_require_approved_assets_exact_roles_and_current_panels(self) -> None:
        for asset_id in ("motion_ref", "location_ref", "state_ref"):
            write_json(
                self.root / "04_assets" / "records" / asset_id / "asset.json",
                {
                    "project_id": "take-me",
                    "asset_id": asset_id,
                    "review_status": "DRAFT",
                    "active": True,
                },
            )
        write_json(
            self.root / "02_storyboard" / "storyboard.json",
            {
                "project_id": "take-me",
                "scene_id": "S01",
                "storyboard_id": "S01_SB001",
                "review_status": "USER_APPROVED",
                "panels": [{"panel_id": "S01_P001", "order": 1, "active_assets": []}],
            },
        )
        write_json(
            self.root / "05_shots" / "S01_SH001" / "shot.json",
            {
                "project_id": "take-me",
                "scene_id": "S01",
                "shot_id": "S01_SH001",
                "review_status": "DRAFT",
                "storyboard_panel_ids": ["S01_P999"],
                "motion_reference_asset_ids": ["motion_ref"],
                "spatial": {"location_asset_id": "location_ref"},
                "continuity": {"state_asset_ids": ["state_ref"]},
                "active_assets": [
                    {"asset_id": "motion_ref", "role": "STYLE"},
                    {"asset_id": "location_ref", "role": "STATE"},
                ],
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["storyboard"] = "02_storyboard/storyboard.json"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_UNAPPROVED_INPUT", codes)
        self.assertIn("E_REFERENCE_ROLE_CONFLICT", codes)
        self.assertIn("UNKNOWN_PANEL", codes)

    def test_boundary_still_evidence_is_byte_bound_and_matches_boundary_assets(self) -> None:
        media_dir = self.root / "04_assets" / "stills"
        media_dir.mkdir(parents=True)
        start_file = media_dir / "start.png"
        end_file = media_dir / "end.png"
        start_file.write_bytes(b"start-frame")
        end_file.write_bytes(b"end-frame")
        start_hash = hashlib.sha256(start_file.read_bytes()).hexdigest()
        end_hash = hashlib.sha256(end_file.read_bytes()).hexdigest()
        for asset_id, media_path, digest in (
            ("start_frame", start_file, start_hash),
            ("end_frame", end_file, end_hash),
        ):
            write_json(
                self.root / "04_assets" / "records" / asset_id / "asset.json",
                {
                    "project_id": "take-me",
                    "asset_id": asset_id,
                    "review_status": "USER_APPROVED",
                    "files": {"immutable_master": {"path": media_path.relative_to(self.root).as_posix(), "sha256": digest}},
                    "lineage": {"output_sha256": digest},
                },
            )
        shot_path = self.root / "05_shots" / "S01_SH001" / "shot.json"
        write_json(
            shot_path,
            {
                "project_id": "take-me",
                "scene_id": "S01",
                "shot_id": "S01_SH001",
                "format_mode": "BOUNDARY_FRAME",
                "active_assets": [
                    {"asset_id": "start_frame", "role": "STATE"},
                    {"asset_id": "end_frame", "role": "STATE"},
                ],
                "boundary_frames": {"start_asset_id": "start_frame", "end_asset_id": "end_frame"},
                "still_evidence": [
                    {"role": "START", "asset_id": "end_frame", "path": end_file.relative_to(self.root).as_posix(), "sha256": end_hash},
                    {"role": "END", "asset_id": "start_frame", "path": start_file.relative_to(self.root).as_posix(), "sha256": "0" * 64},
                ],
            },
        )
        shot_hash = hashlib.sha256(shot_path.read_bytes()).hexdigest()
        write_json(
            self.root / "09_approvals" / "APR_SHOT_STILL_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_SHOT_STILL_0001",
                "subject_type": "SHOT_STILL",
                "subject_id": "S01_SH001",
                "subject_sha256": shot_hash,
                "gate": "SHOT_STILL",
                "review_status": "USER_REVIEW_REQUIRED",
                "requested_by": "director",
                "requested_at": "2026-08-12T00:00:00Z",
                "superseded_by_approval_id": None,
                "evidence": [
                    {
                        "path": shot_path.relative_to(self.root).as_posix(),
                        "sha256": shot_hash,
                        "verified_claim": "exact shot review candidate",
                    }
                ],
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_REFERENCE_ROLE_CONFLICT", codes)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", codes)

    def test_delivery_binds_current_timeline_export_derivation_and_qa_bytes(self) -> None:
        timeline_path = self.root / "07_edit" / "timeline.json"
        export_path = self.root / "08_delivery" / "masters" / "final.mov"
        qa_path = self.root / "08_delivery" / "qa" / "first.png"
        timeline_path.parent.mkdir(parents=True)
        export_path.parent.mkdir(parents=True)
        qa_path.parent.mkdir(parents=True)
        write_json(
            timeline_path,
            {
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 1,
                "supersedes_timeline": None,
                "tracks": [],
                "clips": [],
                "events": [],
                "lock_status": "PICTURE_LOCKED",
            },
        )
        export_path.write_bytes(b"real-export")
        qa_path.write_bytes(b"qa-frame")
        write_json(
            self.root / "08_delivery" / "delivery.json",
            {
                "project_id": "take-me",
                "delivery_id": "final_delivery",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_FINISH_0001",
                "source_timeline": {
                    "timeline_id": "main_timeline",
                    "path": timeline_path.relative_to(self.root).as_posix(),
                    "sha256": "1" * 64,
                },
                "export": {
                    "path": export_path.relative_to(self.root).as_posix(),
                    "sha256": "2" * 64,
                },
                "derivation": {
                    "input_hashes": [{"path": timeline_path.relative_to(self.root).as_posix(), "sha256": "3" * 64}],
                },
                "qa": {
                    "overall_verdict": "PASS",
                    "frame_integrity": {
                        "status": "PASS",
                        "evidence": [{"path": qa_path.relative_to(self.root).as_posix(), "sha256": "4" * 64}],
                    },
                },
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["delivery_record"] = "08_delivery/delivery.json"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in result["errors"]})

    def test_delivery_qa_requires_distinct_first_middle_last_frames_and_truthful_audio_metadata(self) -> None:
        timeline_path = self.root / "07_edit" / "timeline.json"
        export_path = self.root / "08_delivery" / "masters" / "final.mov"
        frame_path = self.root / "08_delivery" / "qa" / "frame.png"
        timeline_path.parent.mkdir(parents=True)
        export_path.parent.mkdir(parents=True)
        frame_path.parent.mkdir(parents=True)
        timeline_path.write_text('{"timeline_id":"main_timeline"}', encoding="utf-8")
        export_path.write_bytes(b"video-container")
        frame_path.write_bytes(b"one-frame-reused-three-times")
        timeline_hash = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        export_hash = hashlib.sha256(export_path.read_bytes()).hexdigest()
        frame_hash = hashlib.sha256(frame_path.read_bytes()).hexdigest()
        frame_evidence = [
            {
                "path": frame_path.relative_to(self.root).as_posix(),
                "sha256": frame_hash,
                "evidence_role": role,
                "frame_or_time": "00:00:01",
            }
            for role in ("FIRST_FRAME", "MIDDLE_FRAME", "LAST_FRAME")
        ]
        delivery_path = self.root / "08_delivery" / "delivery.json"
        write_json(
            delivery_path,
            {
                "project_id": "take-me",
                "delivery_id": "final_delivery",
                "version": 1,
                "supersedes_delivery": None,
                "source_timeline": {"timeline_id": "main_timeline", "path": timeline_path.relative_to(self.root).as_posix(), "sha256": timeline_hash},
                "export": {
                    "path": export_path.relative_to(self.root).as_posix(),
                    "sha256": export_hash,
                    "media": {"audio_present": True, "audio_sample_rate_hz": 48000, "audio_channels": 2},
                },
                "derivation": {"input_hashes": [{"path": timeline_path.relative_to(self.root).as_posix(), "sha256": timeline_hash}]},
                "qa": {
                    "overall_verdict": "PASS",
                    "frame_integrity": {"status": "PASS", "evidence": frame_evidence},
                    "audio_sync": {"status": "PASS", "evidence": [frame_evidence[0]]},
                },
            },
        )
        delivery_hash = hashlib.sha256(delivery_path.read_bytes()).hexdigest()
        write_json(
            self.root / "09_approvals" / "APR_EDIT_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_EDIT_0001",
                "subject_type": "TIMELINE",
                "subject_id": "main_timeline",
                "subject_sha256": timeline_hash,
                "gate": "EDIT",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "director",
                "decided_at": "2026-08-12T00:00:00Z",
                "user_evidence_reference": "timeline-review",
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
                "evidence": [
                    {
                        "path": timeline_path.relative_to(self.root).as_posix(),
                        "sha256": timeline_hash,
                        "verified_claim": "exact picture-locked timeline",
                    }
                ],
            },
        )
        write_json(
            self.root / "09_approvals" / "APR_FINISH_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_FINISH_0001",
                "subject_type": "DELIVERY",
                "subject_id": "final_delivery",
                "subject_sha256": delivery_hash,
                "gate": "FINISH",
                "review_status": "USER_REVIEW_REQUIRED",
                "requested_by": "director",
                "requested_at": "2026-08-12T00:00:00Z",
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
                "evidence": [
                    {
                        "path": delivery_path.relative_to(self.root).as_posix(),
                        "sha256": delivery_hash,
                        "verified_claim": "exact delivery review candidate",
                    }
                ],
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["delivery_record"] = "08_delivery/delivery.json"
        write_json(project_path, project)

        from validate_project import validate_project

        with patch(
            "validate_project.inspect_media",
            return_value={"ok": True, "video_streams": [{"width": 1920, "height": 1080}], "audio_streams": []},
        ):
            result = validate_project(self.root, schema_dir=self.schemas)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("DELIVERY_QA_INVALID", codes)
        self.assertIn("MEDIA_METADATA_MISMATCH", codes)

    def test_collection_gates_cover_every_approved_asset_shot_and_take(self) -> None:
        from validate_project import _check_active_stage_approvals

        cases = (
            ("ASSET_LOCK", "assets", "asset_id", "ASSET", "asset", "output"),
            ("SHOT_STILL", "shots", "shot_id", "SHOT_STILL", "shot", "record"),
            ("RAW_VIDEO", "takes", "take_id", "TAKE", "take", "output"),
        )
        for gate, group, id_key, subject_type, prefix, hash_mode in cases:
            with self.subTest(gate=gate):
                items: list[tuple[dict, Path]] = []
                approvals: list[tuple[dict, Path]] = []
                active: list[str] = []
                for index in (1, 2):
                    identifier = (
                        f"S01_SH{index:03d}" if group == "shots"
                        else f"S01_SH001_T{index:02d}" if group == "takes"
                        else f"asset_{index}"
                    )
                    approval_id = f"APR_{gate}_{index:04d}"
                    record_path = self.root / "records" / gate / f"{index}.json"
                    record = {
                        "project_id": "take-me",
                        id_key: identifier,
                    }
                    if group == "assets":
                        subject_path = self.root / "media" / gate / f"{index}.png"
                        subject_path.parent.mkdir(parents=True, exist_ok=True)
                        subject_path.write_bytes(f"asset-{index}".encode())
                        expected_hash = hashlib.sha256(subject_path.read_bytes()).hexdigest()
                        record["files"] = {
                            "immutable_master": {
                                "path": subject_path.relative_to(self.root).as_posix(),
                                "sha256": expected_hash,
                            }
                        }
                        record["lineage"] = {"output_sha256": expected_hash}
                    elif group == "takes":
                        subject_path = self.root / "media" / gate / f"{index}.mov"
                        subject_path.parent.mkdir(parents=True, exist_ok=True)
                        subject_path.write_bytes(f"take-{index}".encode())
                        expected_hash = hashlib.sha256(subject_path.read_bytes()).hexdigest()
                        record["output_file"] = subject_path.relative_to(self.root).as_posix()
                        record["output_sha256"] = expected_hash
                    write_json(record_path, record)
                    if hash_mode == "record":
                        subject_path = record_path
                        expected_hash = hashlib.sha256(record_path.read_bytes()).hexdigest()
                    approval = {
                        "project_id": "take-me",
                        "approval_id": approval_id,
                        "gate": gate,
                        "subject_type": subject_type,
                        "subject_id": identifier,
                        "subject_sha256": expected_hash,
                        "review_status": "USER_APPROVED",
                        "superseded_by_approval_id": None,
                        "evidence": [
                            {
                                "path": subject_path.relative_to(self.root).as_posix(),
                                "sha256": expected_hash,
                                "verified_claim": "exact current production authority",
                            }
                        ],
                    }
                    items.append((record, record_path))
                    approvals.append((approval, self.root / "09_approvals" / f"{approval_id}.json"))
                    active.append(approval_id)
                records = {
                    key: []
                    for key in ("assets", "shots", "takes", "approvals", "sources", "source_manifests", "storyboards", "timelines", "deliveries")
                }
                records[group] = items
                records["approvals"] = approvals
                project = {
                    "project_id": "take-me",
                    "stage_gates": {name: ("USER_APPROVED" if name == gate else "DRAFT") for name in self.gates},
                    "active_approval_ids": active,
                }
                errors: list[dict] = []
                _check_active_stage_approvals(self.root, project, records, errors)
                self.assertEqual([], errors, (gate, errors))

                project["active_approval_ids"] = active[:1]
                errors = []
                _check_active_stage_approvals(self.root, project, records, errors)
                self.assertIn("E_STAGE_PREREQ", {item["code"] for item in errors})

    def test_singular_gate_uses_only_the_central_approval_for_content_state(self) -> None:
        from validate_project import _check_active_stage_approvals

        board_path = self.root / "02_storyboard" / "storyboard.json"
        board = {
            "project_id": "take-me",
            "storyboard_id": "take_me_board",
            "version": 1,
            "scenes": [],
            "shot_plan": [],
            "asset_plan": [],
        }
        write_json(board_path, board)
        board_hash = hashlib.sha256(board_path.read_bytes()).hexdigest()
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_STORYBOARD_0001",
            "subject_type": "STORYBOARD",
            "subject_id": "take_me_board",
            "subject_sha256": board_hash,
            "gate": "STORYBOARD",
            "review_status": "USER_APPROVED",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": board_path.relative_to(self.root).as_posix(),
                    "sha256": board_hash,
                    "verified_claim": "current storyboard authority",
                }
            ],
        }
        approval_path = self.root / "09_approvals" / "APR_STORYBOARD_0001.json"
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["storyboards"] = [(board, board_path)]
        records["approvals"] = [(approval, approval_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {"storyboard": board_path.relative_to(self.root).as_posix()},
            "stage_gates": {
                gate: ("USER_APPROVED" if gate == "STORYBOARD" else "DRAFT")
                for gate in self.gates
            },
            "active_approval_ids": [approval["approval_id"]],
        }
        errors: list[dict] = []

        _check_active_stage_approvals(self.root, project, records, errors)

        self.assertEqual([], errors)

    def test_non_boundary_still_may_be_pixel_evidence_without_an_asset_record(self) -> None:
        still = self.root / "05_shots" / "S01_SH001" / "review" / "still.png"
        still.parent.mkdir(parents=True)
        still.write_bytes(b"standalone-visible-still")
        write_json(
            self.root / "05_shots" / "S01_SH001" / "shot.json",
            {
                "project_id": "take-me",
                "scene_id": "S01",
                "shot_id": "S01_SH001",
                "format_mode": "REFERENCE_TEXT_NATIVE",
                "review_status": "USER_REVIEW_REQUIRED",
                "approval_id": "APR_SHOT_STILL_0001",
                "active_assets": [],
                "still_evidence": [
                    {
                        "role": "STILL",
                        "asset_id": None,
                        "path": still.relative_to(self.root).as_posix(),
                        "sha256": hashlib.sha256(still.read_bytes()).hexdigest(),
                    }
                ],
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        still_errors = [
            item for item in result["errors"]
            if item["code"] in {"UNKNOWN_ASSET", "E_APPROVAL_HASH_MISMATCH", "E_REFERENCE_ROLE_CONFLICT"}
        ]
        self.assertEqual([], still_errors, result)

    def test_unknown_timeline_source_without_any_shot_is_reported_at_the_timeline(self) -> None:
        write_json(
            self.root / "07_edit" / "timeline.json",
            {
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "tracks": [{"track_id": "TRK_V1", "order": 1}],
                "clips": [
                    {
                        "clip_id": "CLIP_UNKNOWN",
                        "track_id": "TRK_V1",
                        "source_id": "SRC_UNKNOWN",
                        "source_file": "missing.mov",
                        "source_in_frame": 0,
                        "source_out_frame": 10,
                        "timeline_in_frame": 0,
                        "timeline_out_frame": 10,
                    }
                ],
                "events": [],
                "lock_status": "UNLOCKED",
            },
        )

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        unknown = [item for item in result["errors"] if item["code"] == "UNKNOWN_SOURCE"]
        self.assertTrue(unknown, result)
        self.assertTrue(all(item.get("path") == "07_edit/timeline.json" for item in unknown), unknown)

    def test_user_approved_authorities_bind_their_current_json_before_gate_activation(self) -> None:
        stale = self.root / "99_logs" / "stale.json"
        stale.parent.mkdir(parents=True)
        stale.write_text('{"stale":true}', encoding="utf-8")
        stale_hash = hashlib.sha256(stale.read_bytes()).hexdigest()
        authorities = (
            ("02_storyboard/storyboard.json", {"project_id": "take-me", "storyboard_id": "S01_SB001"}, "STORYBOARD", "STORYBOARD", "S01_SB001"),
            ("06_source_library/source_manifest.json", {"project_id": "take-me", "library_id": "approved_sources", "sources": []}, "SOURCE_LIBRARY", "SOURCE_LIBRARY", "approved_sources"),
            ("07_edit/timeline.json", {"project_id": "take-me", "timeline_id": "main_timeline", "tracks": [], "clips": [], "events": []}, "TIMELINE", "EDIT", "main_timeline"),
        )
        for index, (relative, payload, subject_type, gate, subject_id) in enumerate(authorities, start=1):
            approval_id = f"APR_{gate}_{index:04d}"
            write_json(self.root / relative, payload)
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "project_id": "take-me",
                    "approval_id": approval_id,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_sha256": stale_hash,
                    "gate": gate,
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "user_evidence_reference": "stale-proof",
                    "evidence": [{"path": "99_logs/stale.json", "sha256": stale_hash}],
                },
            )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["stage_gates"] = {gate: "DRAFT" for gate in self.gates}
        project["project_status"] = "ACTIVE"
        project["current_stage"] = "STORY"
        project["active_approval_ids"] = []
        project["authority_files"].update(
            {
                "storyboard": "02_storyboard/storyboard.json",
                "source_manifest": "06_source_library/source_manifest.json",
                "timeline": "07_edit/timeline.json",
            }
        )
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        mismatches = [item for item in result["errors"] if item["code"] == "E_APPROVAL_HASH_MISMATCH"]
        self.assertGreaterEqual(len(mismatches), 3, result)

    def test_prose_approval_subject_ids_are_canonical_before_gate_activation(self) -> None:
        story = self.root / "01_story" / "STORY_CONTRACT.md"
        look = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        story.parent.mkdir(parents=True)
        look.parent.mkdir(parents=True)
        story.write_text("story", encoding="utf-8")
        look.write_text("look", encoding="utf-8")
        for index, (target, subject_type, gate, wrong_id) in enumerate(
            ((story, "STORY", "STORY", "arbitrary-story"), (look, "LOOKDEV", "LOOKDEV", "arbitrary-look")),
            start=1,
        ):
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            approval_id = f"APR_{gate}_{index:04d}"
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "project_id": "take-me",
                    "approval_id": approval_id,
                    "subject_type": subject_type,
                    "subject_id": wrong_id,
                    "subject_sha256": digest,
                    "gate": gate,
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "user_evidence_reference": "proof",
                    "evidence": [{"path": target.relative_to(self.root).as_posix(), "sha256": digest}],
                },
            )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["stage_gates"] = {gate: "DRAFT" for gate in self.gates}
        project["project_status"] = "ACTIVE"
        project["current_stage"] = "STORY"
        project["active_approval_ids"] = []
        project["authority_files"].update(
            {"story_contract": "01_story/STORY_CONTRACT.md", "visual_bible": "03_lookdev/VISUAL_BIBLE.md"}
        )
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertGreaterEqual(
            sum(item["code"] == "E_APPROVAL_HASH_MISMATCH" for item in result["errors"]),
            2,
            result,
        )

    def test_storyboard_plan_rejects_missing_shots_unknown_assets_and_unknown_coverage(self) -> None:
        storyboard_path = self.root / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard_path,
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "version": 1,
                "rough_level": 1,
                "story_dependency": None,
                "review_status": "DRAFT",
                "approval_id": None,
                "scenes": [
                    {
                        "scene_id": "S01",
                        "order": 1,
                        "panels": [
                            {
                                "panel_id": "S01_P001",
                                "order": 1,
                                "action": {
                                    "path": {
                                        "waypoints": [
                                            {"order": 1, "label": "start"},
                                            {"order": 1, "label": "end"},
                                        ]
                                    }
                                },
                            }
                        ],
                    },
                    {
                        "scene_id": "S02",
                        "order": 2,
                        "panels": [{"panel_id": "S02_P001", "order": 1}],
                    },
                ],
                "asset_plan": [
                    {
                        "asset_id": "hero",
                        "kind": "CHARACTER",
                        "state_label": "default",
                        "purpose": "Lead character",
                    }
                ],
                "shot_plan": [
                    {
                        "shot_id": "S01_SH001",
                        "scene_id": "S01",
                        "order": 1,
                        "storyboard_panel_ids": ["S01_P001"],
                        "required_asset_ids": ["hero"],
                        "coverage_requirements": [
                            {
                                "coverage_id": "COV_PRIMARY",
                                "kind": "PRIMARY_ACTION",
                                "description": "Primary action coverage",
                                "minimum_approved_takes": 1,
                            }
                        ],
                    },
                    {
                        "shot_id": "S02_SH001",
                        "scene_id": "S02",
                        "order": 1,
                        "storyboard_panel_ids": ["S02_P001"],
                        "required_asset_ids": ["unplanned_moon"],
                        "coverage_requirements": [
                            {
                                "coverage_id": "COV_SECOND",
                                "kind": "REACTION",
                                "description": "Second-scene reaction coverage",
                                "minimum_approved_takes": 1,
                            }
                        ],
                    },
                ],
            },
        )
        write_json(
            self.root / "05_shots" / "S01_SH001" / "shot.json",
            {
                "project_id": "take-me",
                "shot_id": "S01_SH001",
                "scene_id": "S01",
                "review_status": "DRAFT",
                "storyboard_panel_ids": ["S01_P001"],
                "coverage_requirement_ids": ["COV_UNKNOWN"],
                "active_assets": [],
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["storyboard"] = "02_storyboard/storyboard.json"
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        errors = result["errors"]
        self.assertTrue(
            any(item["code"] == "MISSING_PLANNED_SHOT" and "S02_SH001" in item["message"] for item in errors),
            result,
        )
        self.assertTrue(
            any(item["code"] == "UNKNOWN_PLANNED_ASSET" and "unplanned_moon" in item["message"] for item in errors),
            result,
        )
        self.assertTrue(
            any(item["code"] == "UNKNOWN_COVERAGE_REQUIREMENT" and "COV_UNKNOWN" in item["message"] for item in errors),
            result,
        )
        self.assertTrue(
            any(item["code"] == "DUPLICATE_WAYPOINT_ORDER" and "S01_P001" in item["message"] for item in errors),
            result,
        )

    def test_asset_lock_must_exactly_cover_the_storyboard_asset_plan(self) -> None:
        from validate_project import _check_active_stage_approvals

        hero_record_path = self.root / "04_assets" / "records" / "hero" / "asset.json"
        extra_record_path = self.root / "04_assets" / "records" / "scratch" / "asset.json"
        hero_master = self.root / "04_assets" / "masters" / "hero.png"
        scratch_master = self.root / "04_assets" / "masters" / "scratch.png"
        hero_master.parent.mkdir(parents=True, exist_ok=True)
        hero_master.write_bytes(b"hero")
        scratch_master.write_bytes(b"scratch")
        hero_hash = hashlib.sha256(hero_master.read_bytes()).hexdigest()
        scratch_hash = hashlib.sha256(scratch_master.read_bytes()).hexdigest()
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["storyboards"] = [
            (
                {
                    "project_id": "take-me",
                    "storyboard_id": "take_me_board",
                    "asset_plan": [
                        {"asset_id": "hero", "kind": "CHARACTER", "state_label": "default"},
                        {"asset_id": "moon", "kind": "LOCATION", "state_label": "night"},
                    ],
                },
                self.root / "02_storyboard" / "storyboard.json",
            )
        ]
        records["assets"] = [
            (
                {
                    "project_id": "take-me",
                    "asset_id": "hero",
                    "kind": "LOCATION",
                    "state": {"label": "damaged"},
                    "files": {"immutable_master": {"path": hero_master.relative_to(self.root).as_posix(), "sha256": hero_hash}},
                    "lineage": {"output_sha256": hero_hash},
                },
                hero_record_path,
            ),
            (
                {
                    "project_id": "take-me",
                    "asset_id": "scratch",
                    "files": {"immutable_master": {"path": scratch_master.relative_to(self.root).as_posix(), "sha256": scratch_hash}},
                    "lineage": {"output_sha256": scratch_hash},
                },
                extra_record_path,
            ),
        ]
        records["approvals"] = [
            (
                {
                    "project_id": "take-me",
                    "approval_id": "APR_ASSET_LOCK_0001",
                    "gate": "ASSET_LOCK",
                    "subject_type": "ASSET",
                    "subject_id": "hero",
                    "subject_sha256": hero_hash,
                    "review_status": "USER_APPROVED",
                    "superseded_by_approval_id": None,
                    "evidence": [{"path": hero_master.relative_to(self.root).as_posix(), "sha256": hero_hash, "verified_claim": "hero master"}],
                },
                self.root / "09_approvals" / "APR_ASSET_LOCK_0001.json",
            )
        ]
        project = {
            "project_id": "take-me",
            "stage_gates": {"ASSET_LOCK": "USER_APPROVED"},
            "active_approval_ids": ["APR_ASSET_LOCK_0001"],
        }
        errors: list[dict] = []

        _check_active_stage_approvals(self.root, project, records, errors)

        self.assertTrue(
            any("planned asset" in item["message"].lower() and "moon" in item["message"] for item in errors),
            errors,
        )
        self.assertTrue(
            any("scratch" in item["message"] for item in errors),
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

    def test_approved_storyboard_binds_every_nested_panel_image_and_approval_evidence(self) -> None:
        story_path = self.root / "01_story" / "STORY_CONTRACT.md"
        panel_one = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        panel_two = self.root / "02_storyboard" / "panels" / "S02_P001.png"
        for path, content in (
            (story_path, b"approved-story"),
            (panel_one, b"panel-one"),
            (panel_two, b"panel-two"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        story_hash = hashlib.sha256(story_path.read_bytes()).hexdigest()
        storyboard_path = self.root / "02_storyboard" / "storyboard.json"
        write_json(
            storyboard_path,
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "version": 1,
                "rough_level": 1,
                "story_dependency": {
                    "approval_id": "APR_STORY_0001",
                    "path": story_path.relative_to(self.root).as_posix(),
                    "sha256": story_hash,
                },
                "asset_plan": [
                    {"asset_id": "hero", "kind": "CHARACTER", "state_label": "default", "purpose": "Lead"}
                ],
                "scenes": [
                    {
                        "scene_id": "S01",
                        "order": 1,
                        "panels": [
                            {
                                "panel_id": "S01_P001",
                                "order": 1,
                                "image_file": panel_one.relative_to(self.root).as_posix(),
                                "image_sha256": hashlib.sha256(panel_one.read_bytes()).hexdigest(),
                            }
                        ],
                    },
                    {
                        "scene_id": "S02",
                        "order": 2,
                        "panels": [
                            {
                                "panel_id": "S02_P001",
                                "order": 1,
                                "image_file": panel_two.relative_to(self.root).as_posix(),
                                "image_sha256": "0" * 64,
                            }
                        ],
                    },
                ],
                "shot_plan": [
                    {
                        "shot_id": "S01_SH001",
                        "scene_id": "S01",
                        "order": 1,
                        "storyboard_panel_ids": ["S01_P001"],
                        "required_asset_ids": ["hero"],
                        "coverage_requirements": [
                            {
                                "coverage_id": "COV_PRIMARY",
                                "kind": "PRIMARY_ACTION",
                                "description": "Primary action",
                                "minimum_approved_takes": 1,
                            }
                        ],
                    }
                ],
            },
        )
        storyboard_hash = hashlib.sha256(storyboard_path.read_bytes()).hexdigest()
        write_json(
            self.root / "09_approvals" / "APR_STORYBOARD_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_STORYBOARD_0001",
                "subject_type": "STORYBOARD",
                "subject_id": "take_me_board",
                "subject_sha256": storyboard_hash,
                "gate": "STORYBOARD",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "user_evidence_reference": "visible-board-review",
                # Deliberately omits both visible panel images.
                "evidence": [
                    {
                        "path": storyboard_path.relative_to(self.root).as_posix(),
                        "sha256": storyboard_hash,
                    }
                ],
            },
        )
        write_json(
            self.root / "09_approvals" / "APR_STORY_0001.json",
            {
                "project_id": "take-me",
                "approval_id": "APR_STORY_0001",
                "subject_type": "STORY",
                "subject_id": "story-contract",
                "subject_sha256": story_hash,
                "gate": "STORY",
                "review_status": "USER_APPROVED",
                "superseded_by_approval_id": "APR_STORY_0002",
                "decided_by_type": "USER",
                "user_evidence_reference": "older-story-review",
                "evidence": [
                    {
                        "path": story_path.relative_to(self.root).as_posix(),
                        "sha256": story_hash,
                    }
                ],
            },
        )
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update(
            {
                "project_status": "ACTIVE",
                "current_stage": "STORYBOARD",
                "review_status": "DRAFT",
                "stage_gates": {gate: "DRAFT" for gate in self.gates},
                "active_approval_ids": [],
            }
        )
        project["authority_files"].update(
            {
                "story_contract": "01_story/STORY_CONTRACT.md",
                "storyboard": "02_storyboard/storyboard.json",
            }
        )
        write_json(project_path, project)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        self.assertTrue(
            any(
                item["code"] == "E_APPROVAL_HASH_MISMATCH"
                and "panel image bytes" in item["message"].lower()
                and "S02_P001" in item["message"]
                for item in result["errors"]
            ),
            result,
        )
        self.assertTrue(
            any(
                item["code"] == "E_APPROVAL_HASH_MISMATCH"
                and "story_dependency" in item["message"]
                for item in result["errors"]
            ),
            result,
        )
        self.assertTrue(
            any(
                item["code"] == "UNCOVERED_SCENE"
                and "S02" in item["message"]
                for item in result["errors"]
            ),
            result,
        )
        self.assertTrue(
            any(
                item["code"] == "E_APPROVAL_HASH_MISMATCH"
                and "every current panel image" in item["message"].lower()
                for item in result["errors"]
            ),
            result,
        )

    def test_reviewed_delivery_requires_media_integrity_pass(self) -> None:
        from validate_project import _check_deliveries

        timeline_path = self.root / "07_edit" / "timeline.json"
        export_path = self.root / "08_delivery" / "masters" / "final.mov"
        timeline_path.parent.mkdir(parents=True)
        export_path.parent.mkdir(parents=True)
        timeline_path.write_text('{"timeline_id":"main_timeline"}', encoding="utf-8")
        export_path.write_bytes(b"video-container")
        timeline_hash = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        export_hash = hashlib.sha256(export_path.read_bytes()).hexdigest()
        frame_evidence: list[dict] = []
        for index, (role, position) in enumerate(
            (("FIRST_FRAME", "0"), ("MIDDLE_FRAME", "5"), ("LAST_FRAME", "10")),
            start=1,
        ):
            frame_path = self.root / "08_delivery" / "qa" / f"frame-{index}.png"
            frame_path.parent.mkdir(parents=True, exist_ok=True)
            frame_path.write_bytes(f"frame-{index}".encode("ascii"))
            frame_evidence.append(
                {
                    "path": frame_path.relative_to(self.root).as_posix(),
                    "sha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
                    "evidence_role": role,
                    "frame_or_time": position,
                }
            )
        delivery_path = self.root / "08_delivery" / "delivery.json"
        delivery = {
            "project_id": "take-me",
            "delivery_id": "final_delivery",
            "version": 1,
            "supersedes_delivery": None,
            "source_timeline": {
                "timeline_id": "main_timeline",
                "path": timeline_path.relative_to(self.root).as_posix(),
                "sha256": timeline_hash,
            },
            "export": {
                "path": export_path.relative_to(self.root).as_posix(),
                "sha256": export_hash,
                "media": {
                    "width": 1920,
                    "height": 1080,
                    "frame_rate_numerator": 24,
                    "frame_rate_denominator": 1,
                    "duration_seconds": 10.0,
                    "audio_present": False,
                    "audio_sample_rate_hz": None,
                    "audio_channels": None,
                },
            },
            "derivation": {
                "input_hashes": [
                    {
                        "path": timeline_path.relative_to(self.root).as_posix(),
                        "sha256": timeline_hash,
                    }
                ]
            },
            "qa": {
                "overall_verdict": "PASS",
                "media_integrity": {
                    "status": "NOT_APPLICABLE",
                    "reason": "Skipped despite having a rendered export",
                    "evidence": [],
                },
                "frame_integrity": {"status": "PASS", "evidence": frame_evidence},
                "audio_sync": {
                    "status": "NOT_APPLICABLE",
                    "reason": "Export intentionally has no audio",
                    "evidence": [],
                },
            },
        }
        write_json(delivery_path, delivery)
        delivery_hash = hashlib.sha256(delivery_path.read_bytes()).hexdigest()
        edit_approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0001",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": timeline_hash,
            "gate": "EDIT",
            "review_status": "USER_APPROVED",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": timeline_path.relative_to(self.root).as_posix(),
                    "sha256": timeline_hash,
                    "verified_claim": "exact picture-locked timeline",
                }
            ],
        }
        finish_approval = {
            "project_id": "take-me",
            "approval_id": "APR_FINISH_0001",
            "subject_type": "DELIVERY",
            "subject_id": "final_delivery",
            "subject_sha256": delivery_hash,
            "gate": "FINISH",
            "review_status": "USER_REVIEW_REQUIRED",
            "requested_by": "director",
            "requested_at": "2026-08-12T00:00:00Z",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": delivery_path.relative_to(self.root).as_posix(),
                    "sha256": delivery_hash,
                    "verified_claim": "exact delivery candidate",
                }
            ],
        }
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["timelines"] = [
            (
                {
                    "project_id": "take-me",
                    "timeline_id": "main_timeline",
                    "lock_status": "PICTURE_LOCKED",
                },
                timeline_path,
            )
        ]
        records["deliveries"] = [(delivery, delivery_path)]
        records["approvals"] = [
            (edit_approval, self.root / "09_approvals" / "APR_EDIT_0001.json"),
            (finish_approval, self.root / "09_approvals" / "APR_FINISH_0001.json"),
        ]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "delivery_record": "08_delivery/delivery.json",
                "timeline": "07_edit/timeline.json",
            },
        }
        errors: list[dict] = []

        with patch(
            "validate_project.inspect_media",
            return_value={
                "ok": True,
                "video_streams": [
                    {
                        "width": 1920,
                        "height": 1080,
                        "frame_rate": "24/1",
                        "duration_seconds": 10.0,
                    }
                ],
                "audio_streams": [],
                "format": {"duration_seconds": 10.0},
            },
        ):
            _check_deliveries(self.root, project, records, errors)

        self.assertTrue(
            any(
                item["code"] == "DELIVERY_QA_INVALID"
                and "media_integrity" in item["message"]
                for item in errors
            ),
            errors,
        )

        delivery["qa"]["media_integrity"] = {
            "status": "PASS",
            "evidence": [frame_evidence[0]],
        }
        frame_evidence[-1]["frame_or_time"] = "11"
        errors = []
        with patch(
            "validate_project.inspect_media",
            return_value={
                "ok": True,
                "video_streams": [
                    {
                        "width": 1920,
                        "height": 1080,
                        "frame_rate": "24/1",
                        "frame_count": 240,
                        "duration_seconds": 10.0,
                    }
                ],
                "audio_streams": [],
                "format": {"duration_seconds": 10.0},
            },
        ):
            _check_deliveries(self.root, project, records, errors)
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_QA_INVALID"
                and "verified media range" in item["message"]
                for item in errors
            ),
            errors,
        )

    def test_delivery_frame_time_parser_rejects_unsafe_or_ambiguous_values(self) -> None:
        from validate_project import _frame_or_time_position

        for invalid in ("inf", "-1", "99:99", "00:60:00", "frame=-1", "frame=1.5", "1e9999"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(_frame_or_time_position(invalid))
        self.assertEqual(("seconds", 62.5), _frame_or_time_position("01:02.5"))
        self.assertEqual(("frame", 12.0), _frame_or_time_position("frame=12"))

    def test_raw_video_gate_requires_the_storyboard_coverage_minimums(self) -> None:
        from validate_project import _check_active_stage_approvals

        take_path = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.json"
        output_path = take_path.parent / "out.mov"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"take-one")
        output_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["storyboards"] = [
            (
                {
                    "project_id": "take-me",
                    "storyboard_id": "take_me_board",
                    "shot_plan": [
                        {
                            "shot_id": "S01_SH001",
                            "scene_id": "S01",
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
                self.root / "02_storyboard" / "storyboard.json",
            )
        ]
        records["takes"] = [
            (
                {
                    "project_id": "take-me",
                    "take_id": "S01_SH001_T01",
                    "shot_id": "S01_SH001",
                    "coverage_requirement_ids": ["COV_PRIMARY"],
                    "output_file": output_path.relative_to(self.root).as_posix(),
                    "output_sha256": output_hash,
                },
                take_path,
            )
        ]
        records["approvals"] = [
            (
                {
                    "project_id": "take-me",
                    "approval_id": "APR_RAW_VIDEO_0001",
                    "gate": "RAW_VIDEO",
                    "subject_type": "TAKE",
                    "subject_id": "S01_SH001_T01",
                    "subject_sha256": output_hash,
                    "review_status": "USER_APPROVED",
                    "superseded_by_approval_id": None,
                    "evidence": [{"path": output_path.relative_to(self.root).as_posix(), "sha256": output_hash, "verified_claim": "take output"}],
                },
                self.root / "09_approvals" / "APR_RAW_VIDEO_0001.json",
            )
        ]
        project = {
            "project_id": "take-me",
            "stage_gates": {"RAW_VIDEO": "USER_APPROVED"},
            "active_approval_ids": ["APR_RAW_VIDEO_0001"],
        }
        errors: list[dict] = []

        _check_active_stage_approvals(self.root, project, records, errors)

        self.assertTrue(
            any(
                item["code"] == "COVERAGE_MINIMUM_NOT_MET"
                and "COV_PRIMARY" in item["message"]
                and "2" in item["message"]
                for item in errors
            ),
            errors,
        )

    def test_review_ready_shot_snapshot_binds_current_authorities_and_exact_planned_assets(self) -> None:
        story_path = self.root / "01_story" / "STORY_CONTRACT.md"
        board_path = self.root / "02_storyboard" / "storyboard.json"
        look_path = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        asset_master = self.root / "04_assets" / "masters" / "hero.png"
        asset_record_path = self.root / "04_assets" / "records" / "hero" / "asset.json"
        shot_path = self.root / "05_shots" / "S01_SH001" / "shot.json"
        for path, content in (
            (story_path, b"story"),
            (look_path, b"look"),
            (asset_master, b"hero"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        story_hash = hashlib.sha256(story_path.read_bytes()).hexdigest()
        look_hash = hashlib.sha256(look_path.read_bytes()).hexdigest()
        asset_hash = hashlib.sha256(asset_master.read_bytes()).hexdigest()
        storyboard = {
            "project_id": "take-me",
            "storyboard_id": "take_me_board",
            "shot_plan": [
                {
                    "shot_id": "S01_SH001",
                    "scene_id": "S01",
                    "storyboard_panel_ids": ["S01_P001"],
                    "required_asset_ids": ["hero"],
                    "coverage_requirements": [
                        {
                            "coverage_id": "COV_PRIMARY",
                            "kind": "PRIMARY_ACTION",
                            "description": "Primary action",
                            "minimum_approved_takes": 1,
                        }
                    ],
                }
            ],
        }
        write_json(board_path, storyboard)
        board_hash = hashlib.sha256(board_path.read_bytes()).hexdigest()
        asset = {
            "project_id": "take-me",
            "asset_id": "hero",
            "review_status": "USER_APPROVED",
            "approval_id": "APR_ASSET_LOCK_0001",
            "files": {
                "immutable_master": {
                    "path": asset_master.relative_to(self.root).as_posix(),
                    "sha256": asset_hash,
                }
            },
            "lineage": {"output_sha256": asset_hash},
        }
        write_json(asset_record_path, asset)

        approval_specs = (
            ("APR_STORY_0001", "STORY", "story-contract", "STORY", story_path, story_hash),
            ("APR_STORYBOARD_0001", "STORYBOARD", "take_me_board", "STORYBOARD", board_path, board_hash),
            ("APR_LOOKDEV_0001", "LOOKDEV", "visual-bible", "LOOKDEV", look_path, look_hash),
            ("APR_ASSET_LOCK_0001", "ASSET", "hero", "ASSET_LOCK", asset_master, asset_hash),
        )
        approvals: list[tuple[dict, Path]] = []
        for approval_id, subject_type, subject_id, gate, authority, digest in approval_specs:
            approval_path = self.root / "09_approvals" / f"{approval_id}.json"
            approval = {
                "project_id": "take-me",
                "approval_id": approval_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "subject_sha256": digest,
                "gate": gate,
                "review_status": "USER_APPROVED",
                "evidence": [
                    {
                        "path": authority.relative_to(self.root).as_posix(),
                        "sha256": digest,
                    }
                ],
            }
            write_json(approval_path, approval)
            approvals.append((approval, approval_path))

        def binding(
            subject_type: str,
            subject_id: str,
            approval_id: str,
            authority: Path,
            digest: str,
        ) -> dict:
            return {
                "subject_type": subject_type,
                "subject_id": subject_id,
                "approval_id": approval_id,
                "review_status": "USER_APPROVED",
                "subject_sha256": digest,
                "authority_path": authority.relative_to(self.root).as_posix(),
                "approval_record_path": f"09_approvals/{approval_id}.json",
            }

        shot = {
            "project_id": "take-me",
            "scene_id": "S01",
            "shot_id": "S01_SH001",
            "storyboard_panel_ids": ["S01_P001"],
            "coverage_requirement_ids": ["COV_UNKNOWN"],
            "dependency_snapshot": {
                "project_id": "take-me",
                "captured_at": "2026-08-11T00:00:00Z",
                "story": binding("STORY", "story-contract", "APR_STORY_0001", story_path, story_hash),
                "storyboard": binding("STORYBOARD", "take_me_board", "APR_STORYBOARD_0001", board_path, board_hash),
                "lookdev": binding("LOOKDEV", "visual-bible", "APR_LOOKDEV_0001", look_path, "0" * 64),
                # Deliberately omits the planned required hero asset.
                "required_assets": [],
            },
        }
        write_json(shot_path, shot)
        shot_hash = hashlib.sha256(shot_path.read_bytes()).hexdigest()
        shot_approval_path = self.root / "09_approvals" / "APR_SHOT_STILL_0001.json"
        shot_approval = {
            "project_id": "take-me",
            "approval_id": "APR_SHOT_STILL_0001",
            "subject_type": "SHOT_STILL",
            "subject_id": "S01_SH001",
            "subject_sha256": shot_hash,
            "gate": "SHOT_STILL",
            "review_status": "USER_REVIEW_REQUIRED",
            "requested_by": "director",
            "requested_at": "2026-08-12T00:00:00Z",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": shot_path.relative_to(self.root).as_posix(),
                    "sha256": shot_hash,
                    "verified_claim": "exact shot candidate",
                }
            ],
        }
        write_json(shot_approval_path, shot_approval)
        approvals.append((shot_approval, shot_approval_path))
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["assets"] = [(asset, asset_record_path)]
        records["shots"] = [(shot, shot_path)]
        records["storyboards"] = [(storyboard, board_path)]
        records["approvals"] = approvals
        project = {
            "project_id": "take-me",
            "authority_files": {
                "story_contract": story_path.relative_to(self.root).as_posix(),
                "storyboard": board_path.relative_to(self.root).as_posix(),
                "visual_bible": look_path.relative_to(self.root).as_posix(),
            },
        }

        from validate_project import _check_shot_dependency_snapshots

        errors: list[dict] = []
        _check_shot_dependency_snapshots(self.root, project, records, errors)
        self.assertTrue(
            any(item["code"] == "DEPENDENCY_SNAPSHOT_STALE" and "lookdev" in item["message"].lower() for item in errors),
            errors,
        )
        self.assertTrue(
            any(item["code"] == "DEPENDENCY_SNAPSHOT_STALE" and "required asset" in item["message"].lower() for item in errors),
            errors,
        )
        self.assertTrue(
            any(item["code"] == "DEPENDENCY_SNAPSHOT_STALE" and "coverage" in item["message"].lower() for item in errors),
            errors,
        )

        approvals[1][0]["review_status"] = "REJECTED"
        draft_storyboard_errors: list[dict] = []
        _check_shot_dependency_snapshots(self.root, project, records, draft_storyboard_errors)
        self.assertTrue(
            any(
                item["code"] == "DEPENDENCY_SNAPSHOT_STALE"
                and "storyboard" in item["message"].lower()
                for item in draft_storyboard_errors
            ),
            draft_storyboard_errors,
        )

        approvals[1][0]["review_status"] = "USER_APPROVED"
        approvals[1][0]["superseded_by_approval_id"] = "APR_STORYBOARD_0002"
        superseded_storyboard_errors: list[dict] = []
        _check_shot_dependency_snapshots(
            self.root,
            project,
            records,
            superseded_storyboard_errors,
        )
        self.assertTrue(
            any(
                item["code"] == "DEPENDENCY_SNAPSHOT_STALE"
                and "storyboard" in item["message"].lower()
                for item in superseded_storyboard_errors
            ),
            superseded_storyboard_errors,
        )

    def test_timeline_revision_requires_lock_equivalence_current_pointer_and_immediate_predecessor(self) -> None:
        timeline_v1_path = self.root / "07_edit" / "timeline.json"
        timeline_v1 = {
            "schema_id": "cinema-studio-pipeline/timeline@2.0.0",
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "supersedes_timeline": None,
            "tracks": [],
            "clips": [],
            "events": [],
            "lock_status": "PICTURE_LOCKED",
        }
        write_json(timeline_v1_path, timeline_v1)
        timeline_v1_hash = hashlib.sha256(timeline_v1_path.read_bytes()).hexdigest()
        timeline_v2_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v2 = {
            "schema_id": "cinema-studio-pipeline/timeline@2.0.0",
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 2,
            "supersedes_timeline": {
                "timeline_id": "main_timeline",
                "version": 1,
                "path": "07_edit/timeline.json",
                "sha256": "0" * 64,
                "approval_id": "APR_EDIT_0001",
            },
            "tracks": [],
            "clips": [],
            "events": [],
            # Deliberately exposes a central review candidate before locking.
            "lock_status": "UNLOCKED",
        }
        write_json(timeline_v2_path, timeline_v2)
        timeline_v2_hash = hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest()
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"]["timeline"] = timeline_v2_path.relative_to(self.root).as_posix()
        write_json(project_path, project)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["timelines"] = [(timeline_v2, timeline_v2_path), (timeline_v1, timeline_v1_path)]
        records["approvals"] = [
            (
                {
                    "project_id": "take-me",
                    "approval_id": "APR_EDIT_0001",
                    "subject_type": "TIMELINE",
                    "subject_id": "main_timeline",
                    "subject_sha256": timeline_v1_hash,
                    "gate": "EDIT",
                    "review_status": "USER_APPROVED",
                    "superseded_by_approval_id": None,
                    "evidence": [
                        {
                            "path": timeline_v1_path.relative_to(self.root).as_posix(),
                            "sha256": timeline_v1_hash,
                            "verified_claim": "exact timeline v1",
                        }
                    ],
                },
                self.root / "09_approvals" / "APR_EDIT_0001.json",
            ),
            (
                {
                    "project_id": "take-me",
                    "approval_id": "APR_EDIT_0002",
                    "subject_type": "TIMELINE",
                    "subject_id": "main_timeline",
                    "subject_sha256": timeline_v2_hash,
                    "gate": "EDIT",
                    "review_status": "USER_REVIEW_REQUIRED",
                    "superseded_by_approval_id": None,
                    "evidence": [
                        {
                            "path": timeline_v2_path.relative_to(self.root).as_posix(),
                            "sha256": timeline_v2_hash,
                            "verified_claim": "exact unlocked candidate for negative test",
                        }
                    ],
                },
                self.root / "09_approvals" / "APR_EDIT_0002.json",
            ),
        ]

        from validate_project import _check_timeline_revisions

        errors: list[dict] = []
        _check_timeline_revisions(self.root, project, records, errors)
        self.assertTrue(
            any(item["code"] == "TIMELINE_LOCK_INVALID" for item in errors),
            errors,
        )
        self.assertTrue(
            any(item["code"] == "TIMELINE_PREDECESSOR_INVALID" for item in errors),
            errors,
        )

        timeline_v3_path = self.root / "07_edit" / "records" / "main_timeline" / "v003" / "timeline.json"
        timeline_v3 = {
            **timeline_v2,
            "version": 3,
            "lock_status": "UNLOCKED",
            "supersedes_timeline": {
                "timeline_id": "main_timeline",
                "version": 2,
                "path": timeline_v2_path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest(),
                "approval_id": "APR_EDIT_0002",
            },
        }
        write_json(timeline_v3_path, timeline_v3)
        stale_pointer_errors: list[dict] = []
        records["timelines"].insert(0, (timeline_v3, timeline_v3_path))
        _check_timeline_revisions(self.root, project, records, stale_pointer_errors)
        self.assertTrue(
            any(
                item["code"] == "TIMELINE_POINTER_INVALID"
                and "newest" in item["message"].lower()
                for item in stale_pointer_errors
            ),
            stale_pointer_errors,
        )

    def test_delivery_revisions_require_exact_current_timeline_and_latest_canonical_pointer(self) -> None:
        from validate_project import _check_deliveries

        timeline_v1_path = self.root / "07_edit" / "timeline.json"
        timeline_v2_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v1 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "lock_status": "PICTURE_LOCKED",
        }
        timeline_v2 = {
            **timeline_v1,
            "version": 2,
        }
        write_json(timeline_v1_path, timeline_v1)
        write_json(timeline_v2_path, timeline_v2)
        timeline_v2_hash = hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest()

        delivery_v1_path = self.root / "08_delivery" / "delivery.json"
        delivery_v1 = {
            "project_id": "take-me",
            "delivery_id": "final_delivery",
            "version": 1,
            "supersedes_delivery": None,
            "review_status": "USER_APPROVED",
            "approval_id": "APR_FINISH_0001",
            "source_timeline": {
                "timeline_id": "main_timeline",
                "path": timeline_v2_path.relative_to(self.root).as_posix(),
                "sha256": timeline_v2_hash,
            },
            "export": {},
            "derivation": {
                "input_hashes": [
                    {
                        "path": timeline_v2_path.relative_to(self.root).as_posix(),
                        "sha256": timeline_v2_hash,
                    }
                ]
            },
            "qa": {},
        }
        write_json(delivery_v1_path, delivery_v1)
        delivery_v1_hash = hashlib.sha256(delivery_v1_path.read_bytes()).hexdigest()
        delivery_v2_path = self.root / "08_delivery" / "records" / "final_delivery" / "v002" / "delivery.json"
        delivery_v2 = {
            **delivery_v1,
            "version": 2,
            "review_status": "DRAFT",
            "approval_id": None,
            "supersedes_delivery": {
                "delivery_id": "final_delivery",
                "version": 1,
                "path": delivery_v1_path.relative_to(self.root).as_posix(),
                "sha256": delivery_v1_hash,
                "approval_id": "APR_FINISH_0001",
            },
        }
        write_json(delivery_v2_path, delivery_v2)
        approval_path = self.root / "09_approvals" / "APR_FINISH_0001.json"
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_FINISH_0001",
            "subject_type": "DELIVERY",
            "subject_id": "final_delivery",
            "subject_sha256": delivery_v1_hash,
            "gate": "FINISH",
            "review_status": "USER_APPROVED",
            "evidence": [
                {
                    "path": delivery_v1_path.relative_to(self.root).as_posix(),
                    "sha256": delivery_v1_hash,
                }
            ],
        }
        write_json(approval_path, approval)
        edit_approval_path = self.root / "09_approvals" / "APR_EDIT_0002.json"
        edit_approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0002",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": timeline_v2_hash,
            "gate": "EDIT",
            "review_status": "USER_APPROVED",
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": timeline_v2_path.relative_to(self.root).as_posix(),
                    "sha256": timeline_v2_hash,
                    "verified_claim": "exact picture-locked edit",
                }
            ],
        }
        write_json(edit_approval_path, edit_approval)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        # Deliberately put v1 last. Selection by timeline_id alone chooses the
        # wrong revision even though source_timeline carries an exact path/hash.
        records["timelines"] = [(timeline_v2, timeline_v2_path), (timeline_v1, timeline_v1_path)]
        records["deliveries"] = [(delivery_v2, delivery_v2_path), (delivery_v1, delivery_v1_path)]
        records["approvals"] = [(approval, approval_path), (edit_approval, edit_approval_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "timeline": timeline_v2_path.relative_to(self.root).as_posix(),
                # Deliberately stale: a v2 record exists.
                "delivery_record": delivery_v1_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []
        with patch("validate_project.inspect_media", return_value={"ok": False, "errors": []}):
            _check_deliveries(self.root, project, records, errors)

        self.assertFalse(
            any("current delivery must bind" in item["message"].lower() for item in errors),
            errors,
        )
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_POINTER_INVALID"
                and "newest" in item["message"].lower()
                for item in errors
            ),
            errors,
        )

        arbitrary_v1_path = self.root / "08_delivery" / "records" / "wrong" / "delivery.json"
        write_json(arbitrary_v1_path, delivery_v1)
        arbitrary_records = {key: list(value) for key, value in records.items()}
        arbitrary_records["deliveries"] = [(delivery_v1, arbitrary_v1_path)]
        arbitrary_project = {
            **project,
            "authority_files": {
                **project["authority_files"],
                "delivery_record": arbitrary_v1_path.relative_to(self.root).as_posix(),
            },
        }
        arbitrary_errors: list[dict] = []
        _check_deliveries(self.root, arbitrary_project, arbitrary_records, arbitrary_errors)
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_POINTER_INVALID"
                and "v1" in item["message"].lower()
                for item in arbitrary_errors
            ),
            arbitrary_errors,
        )

        missing_pointer_project = {
            **project,
            "authority_files": {
                **project["authority_files"],
                "delivery_record": "08_delivery/missing.json",
            },
        }
        missing_pointer_errors: list[dict] = []
        _check_deliveries(self.root, missing_pointer_project, records, missing_pointer_errors)
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_POINTER_INVALID"
                and "discovered" in item["message"].lower()
                for item in missing_pointer_errors
            ),
            missing_pointer_errors,
        )

        cross_chain_path = self.root / "08_delivery" / "records" / "other_delivery" / "v002" / "delivery.json"
        cross_chain_delivery = {
            **delivery_v2,
            "delivery_id": "other_delivery",
            # Deliberately claims final_delivery v1 as its predecessor.
            "supersedes_delivery": dict(delivery_v2["supersedes_delivery"]),
        }
        write_json(cross_chain_path, cross_chain_delivery)
        cross_chain_records = {key: list(value) for key, value in records.items()}
        cross_chain_records["deliveries"] = [
            (cross_chain_delivery, cross_chain_path),
            (delivery_v1, delivery_v1_path),
        ]
        cross_chain_project = {
            **project,
            "authority_files": {
                **project["authority_files"],
                "delivery_record": cross_chain_path.relative_to(self.root).as_posix(),
            },
        }
        cross_chain_errors: list[dict] = []
        _check_deliveries(self.root, cross_chain_project, cross_chain_records, cross_chain_errors)
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_PREDECESSOR_INVALID"
                and "same delivery chain" in item["message"].lower()
                for item in cross_chain_errors
            ),
            cross_chain_errors,
        )

        copied_predecessor_path = self.root / "misc" / "copied-delivery-v1.json"
        write_json(copied_predecessor_path, delivery_v1)
        copied_predecessor_hash = hashlib.sha256(copied_predecessor_path.read_bytes()).hexdigest()
        copied_predecessor_delivery = {
            **delivery_v2,
            "supersedes_delivery": {
                **delivery_v2["supersedes_delivery"],
                "path": copied_predecessor_path.relative_to(self.root).as_posix(),
                "sha256": copied_predecessor_hash,
            },
        }
        write_json(delivery_v2_path, copied_predecessor_delivery)
        copied_predecessor_records = {key: list(value) for key, value in records.items()}
        copied_predecessor_records["deliveries"] = [
            (copied_predecessor_delivery, delivery_v2_path),
            (delivery_v1, delivery_v1_path),
        ]
        copied_predecessor_project = {
            **project,
            "authority_files": {
                **project["authority_files"],
                "delivery_record": delivery_v2_path.relative_to(self.root).as_posix(),
            },
        }
        copied_predecessor_errors: list[dict] = []
        _check_deliveries(
            self.root,
            copied_predecessor_project,
            copied_predecessor_records,
            copied_predecessor_errors,
        )
        self.assertTrue(
            any(
                item["code"] == "DELIVERY_PREDECESSOR_INVALID"
                and "authoritative" in item["message"].lower()
                for item in copied_predecessor_errors
            ),
            copied_predecessor_errors,
        )

        write_json(delivery_v2_path, delivery_v2)

        approved_v2 = {
            **delivery_v2,
            "review_status": "USER_APPROVED",
            "approval_id": "APR_FINISH_0002",
        }
        write_json(delivery_v2_path, approved_v2)
        approved_v2_hash = hashlib.sha256(delivery_v2_path.read_bytes()).hexdigest()
        new_approval_path = self.root / "09_approvals" / "APR_FINISH_0002.json"
        new_approval = {
            **approval,
            "approval_id": "APR_FINISH_0002",
            "subject_sha256": approved_v2_hash,
            "supersedes_approval_id": None,
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": delivery_v2_path.relative_to(self.root).as_posix(),
                    "sha256": approved_v2_hash,
                }
            ],
        }
        approval["supersedes_approval_id"] = None
        approval["superseded_by_approval_id"] = None
        write_json(new_approval_path, new_approval)
        approved_records = {key: list(value) for key, value in records.items()}
        approved_records["deliveries"] = [
            (approved_v2, delivery_v2_path),
            (delivery_v1, delivery_v1_path),
        ]
        approved_records["approvals"] = [
            (approval, approval_path),
            (new_approval, new_approval_path),
            (edit_approval, edit_approval_path),
        ]
        approved_project = {
            **project,
            "authority_files": {
                **project["authority_files"],
                "delivery_record": delivery_v2_path.relative_to(self.root).as_posix(),
            },
        }
        unlinked_errors: list[dict] = []
        _check_deliveries(self.root, approved_project, approved_records, unlinked_errors)
        self.assertTrue(
            any(item["code"] == "DELIVERY_APPROVAL_CHAIN_INVALID" for item in unlinked_errors),
            unlinked_errors,
        )

        approval["superseded_by_approval_id"] = "APR_FINISH_0002"
        new_approval["supersedes_approval_id"] = "APR_FINISH_0001"
        linked_delivery_errors: list[dict] = []
        _check_deliveries(
            self.root,
            approved_project,
            approved_records,
            linked_delivery_errors,
        )
        self.assertFalse(
            any(item["code"] == "DELIVERY_APPROVAL_CHAIN_INVALID" for item in linked_delivery_errors),
            linked_delivery_errors,
        )

    def test_timeline_revision_requires_bidirectional_approval_replacement_links(self) -> None:
        from validate_project import _check_timeline_revisions

        timeline_v1_path = self.root / "07_edit" / "timeline.json"
        timeline_v1 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "supersedes_timeline": None,
            "lock_status": "PICTURE_LOCKED",
        }
        write_json(timeline_v1_path, timeline_v1)
        timeline_v1_hash = hashlib.sha256(timeline_v1_path.read_bytes()).hexdigest()
        timeline_v2_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v2 = {
            **timeline_v1,
            "version": 2,
            "supersedes_timeline": {
                "timeline_id": "main_timeline",
                "version": 1,
                "path": timeline_v1_path.relative_to(self.root).as_posix(),
                "sha256": timeline_v1_hash,
                "approval_id": "APR_EDIT_0001",
            },
        }
        write_json(timeline_v2_path, timeline_v2)
        timeline_v2_hash = hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest()
        old_approval_path = self.root / "09_approvals" / "APR_EDIT_0001.json"
        new_approval_path = self.root / "09_approvals" / "APR_EDIT_0002.json"
        old_approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0001",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": timeline_v1_hash,
            "gate": "EDIT",
            "review_status": "USER_APPROVED",
            "supersedes_approval_id": None,
            "superseded_by_approval_id": None,
            "evidence": [
                {
                    "path": timeline_v1_path.relative_to(self.root).as_posix(),
                    "sha256": timeline_v1_hash,
                    "verified_claim": "exact timeline v1",
                }
            ],
        }
        new_approval = {
            **old_approval,
            "approval_id": "APR_EDIT_0002",
            "subject_sha256": timeline_v2_hash,
            "evidence": [
                {
                    "path": timeline_v2_path.relative_to(self.root).as_posix(),
                    "sha256": timeline_v2_hash,
                    "verified_claim": "exact timeline v2",
                }
            ],
        }
        write_json(old_approval_path, old_approval)
        write_json(new_approval_path, new_approval)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["timelines"] = [(timeline_v2, timeline_v2_path), (timeline_v1, timeline_v1_path)]
        records["approvals"] = [
            (old_approval, old_approval_path),
            (new_approval, new_approval_path),
        ]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "timeline": timeline_v2_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []
        _check_timeline_revisions(self.root, project, records, errors)
        self.assertTrue(
            any(item["code"] == "TIMELINE_APPROVAL_CHAIN_INVALID" for item in errors),
            errors,
        )

        old_approval["superseded_by_approval_id"] = "APR_EDIT_0002"
        new_approval["supersedes_approval_id"] = "APR_EDIT_0001"
        write_json(old_approval_path, old_approval)
        write_json(new_approval_path, new_approval)
        linked_errors: list[dict] = []
        _check_timeline_revisions(self.root, project, records, linked_errors)
        self.assertFalse(
            any(item["code"] == "TIMELINE_APPROVAL_CHAIN_INVALID" for item in linked_errors),
            linked_errors,
        )

        draft_timeline = {
            **timeline_v2,
            "lock_status": "UNLOCKED",
        }
        write_json(timeline_v2_path, draft_timeline)
        old_approval["superseded_by_approval_id"] = None
        draft_records = {key: list(value) for key, value in records.items()}
        draft_records["timelines"] = [
            (draft_timeline, timeline_v2_path),
            (timeline_v1, timeline_v1_path),
        ]
        draft_records["approvals"] = [(old_approval, old_approval_path)]
        draft_errors: list[dict] = []
        _check_timeline_revisions(self.root, project, draft_records, draft_errors)
        self.assertFalse(
            any(item["code"] == "TIMELINE_APPROVAL_CHAIN_INVALID" for item in draft_errors),
            draft_errors,
        )

    def test_active_edit_gate_resolves_the_exact_current_timeline_pointer(self) -> None:
        from validate_project import _check_active_stage_approvals

        timeline_v1_path = self.root / "07_edit" / "timeline.json"
        timeline_v2_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v1 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "review_status": "USER_APPROVED",
            "approval_id": "APR_EDIT_0001",
        }
        timeline_v2 = {
            **timeline_v1,
            "version": 2,
            "approval_id": "APR_EDIT_0002",
        }
        write_json(timeline_v1_path, timeline_v1)
        write_json(timeline_v2_path, timeline_v2)
        timeline_v2_hash = hashlib.sha256(timeline_v2_path.read_bytes()).hexdigest()
        approval_path = self.root / "09_approvals" / "APR_EDIT_0002.json"
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_EDIT_0002",
            "gate": "EDIT",
            "subject_type": "TIMELINE",
            "subject_id": "main_timeline",
            "subject_sha256": timeline_v2_hash,
            "review_status": "USER_APPROVED",
        }
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        # Historical record first exposes any order-dependent authority lookup.
        records["timelines"] = [(timeline_v1, timeline_v1_path), (timeline_v2, timeline_v2_path)]
        records["approvals"] = [(approval, approval_path)]
        project = {
            "project_id": "take-me",
            "stage_gates": {"EDIT": "USER_APPROVED"},
            "active_approval_ids": ["APR_EDIT_0002"],
            "authority_files": {
                "timeline": timeline_v2_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []

        _check_active_stage_approvals(self.root, project, records, errors)

        self.assertEqual([], errors)

        approval["superseded_by_approval_id"] = "APR_EDIT_0003"
        superseded_errors: list[dict] = []
        _check_active_stage_approvals(self.root, project, records, superseded_errors)
        self.assertTrue(
            any(item["code"] == "E_STAGE_PREREQ" for item in superseded_errors),
            superseded_errors,
        )

        from validate_project import _check_approval_gates

        record_approval_errors: list[dict] = []
        current_only_records = {key: list(value) for key, value in records.items()}
        current_only_records["timelines"] = [(timeline_v2, timeline_v2_path)]
        _check_approval_gates(
            self.root,
            project,
            current_only_records,
            record_approval_errors,
        )
        self.assertEqual([], record_approval_errors)

    def test_downstream_approvals_and_take_inputs_bind_immediate_prerequisite_bytes(self) -> None:
        project_path = self.root / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project.update(
            {
                "project_status": "ACTIVE",
                "current_stage": "STORY",
                "review_status": "DRAFT",
                "stage_gates": {gate: "DRAFT" for gate in self.gates},
                "active_approval_ids": [],
            }
        )
        project["authority_files"].update(
            {
                "story_contract": "01_story/STORY_CONTRACT.md",
                "storyboard": "02_storyboard/storyboard.json",
                "visual_bible": "03_lookdev/VISUAL_BIBLE.md",
            }
        )
        write_json(project_path, project)

        story_path = self.root / "01_story" / "STORY_CONTRACT.md"
        board_path = self.root / "02_storyboard" / "storyboard.json"
        look_path = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        asset_path = self.root / "04_assets" / "masters" / "hero.png"
        shot_path = self.root / "05_shots" / "S01_SH001" / "shot.json"
        take_output = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.mov"
        for path, content in (
            (story_path, b"current-story"),
            (look_path, b"current-look"),
            (asset_path, b"current-asset"),
            (take_output, b"current-take"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        write_json(
            board_path,
            {
                "project_id": "take-me",
                "storyboard_id": "take_me_board",
                "version": 1,
                "rough_level": 1,
                "story_dependency": None,
                "review_status": "USER_APPROVED",
                "approval_id": "APR_STORYBOARD_0001",
                "scenes": [],
                "asset_plan": [],
                "shot_plan": [],
            },
        )
        write_json(
            self.root / "04_assets" / "records" / "hero" / "asset.json",
            {
                "project_id": "take-me",
                "asset_id": "hero",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_ASSET_LOCK_0001",
                "files": {
                    "immutable_master": {
                        "path": asset_path.relative_to(self.root).as_posix(),
                        "sha256": hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                    }
                },
                "lineage": {"output_sha256": hashlib.sha256(asset_path.read_bytes()).hexdigest()},
            },
        )
        write_json(
            shot_path,
            {
                "project_id": "take-me",
                "scene_id": "S01",
                "shot_id": "S01_SH001",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_SHOT_STILL_0001",
                "format_mode": "REFERENCE_TEXT_NATIVE",
                "active_assets": [],
                "storyboard_panel_ids": [],
                "still_evidence": [],
            },
        )
        write_json(
            self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "take.json",
            {
                "project_id": "take-me",
                "take_id": "S01_SH001_T01",
                "shot_id": "S01_SH001",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_RAW_VIDEO_0001",
                "execution_origin": "LOCAL_PROCESSING",
                "output_file": take_output.relative_to(self.root).as_posix(),
                "output_sha256": hashlib.sha256(take_output.read_bytes()).hexdigest(),
                "input_hashes": [],
                "lineage": {"source_asset_ids": ["hero"], "source_take_ids": [], "parent_take_id": None},
                "model": {"verified": True, "version": "1"},
                "generation_parameters": {"tool": "local"},
                "remote": {"verified": False, "job_id": None},
                "remote_job_id": None,
                "diagnosis": {"verdict": "PASS"},
            },
        )
        source_manifest_path = self.root / "06_source_library" / "source_manifest.json"
        write_json(
            source_manifest_path,
            {
                "project_id": "take-me",
                "library_id": "source_library",
                "review_status": "USER_APPROVED",
                "approval_id": "APR_SOURCE_LIBRARY_0001",
                "lock_status": "SOURCE_LOCKED",
                "sources": [],
            },
        )
        timeline_path = self.root / "07_edit" / "timeline.json"
        write_json(
            timeline_path,
            {
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 1,
                "supersedes_timeline": None,
                "review_status": "USER_APPROVED",
                "approval_id": "APR_EDIT_0001",
                "lock_status": "PICTURE_LOCKED",
                "tracks": [],
                "clips": [],
                "events": [],
            },
        )

        def approval(
            approval_id: str,
            subject_type: str,
            subject_id: str,
            gate: str,
            subject_path: Path,
        ) -> None:
            digest = hashlib.sha256(subject_path.read_bytes()).hexdigest()
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "project_id": "take-me",
                    "approval_id": approval_id,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "subject_sha256": digest,
                    "gate": gate,
                    "review_status": "USER_APPROVED",
                    "decided_by_type": "USER",
                    "decided_by": "owner",
                    "decided_at": "2026-08-11T00:00:00Z",
                    "user_evidence_reference": "visible-review",
                    # Deliberately only bind the subject. Downstream approvals must
                    # also carry their immediate prerequisite authority evidence.
                    "evidence": [
                        {
                            "path": subject_path.relative_to(self.root).as_posix(),
                            "sha256": digest,
                        }
                    ],
                },
            )

        approval("APR_STORY_0001", "STORY", "story-contract", "STORY", story_path)
        approval("APR_STORYBOARD_0001", "STORYBOARD", "take_me_board", "STORYBOARD", board_path)
        approval("APR_LOOKDEV_0001", "LOOKDEV", "visual-bible", "LOOKDEV", look_path)
        approval("APR_ASSET_LOCK_0001", "ASSET", "hero", "ASSET_LOCK", asset_path)
        approval("APR_SHOT_STILL_0001", "SHOT_STILL", "S01_SH001", "SHOT_STILL", shot_path)
        approval("APR_RAW_VIDEO_0001", "TAKE", "S01_SH001_T01", "RAW_VIDEO", take_output)
        approval(
            "APR_SOURCE_LIBRARY_0001",
            "SOURCE_LIBRARY",
            "source_library",
            "SOURCE_LIBRARY",
            source_manifest_path,
        )
        # Deliberately omits the source manifest prerequisite evidence.
        approval("APR_EDIT_0001", "TIMELINE", "main_timeline", "EDIT", timeline_path)

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=self.schemas)
        messages = [item["message"].lower() for item in result["errors"]]
        for expected in (
            "storyboard approval evidence must include current story contract",
            "lookdev approval evidence must include current storyboard",
            "asset approval evidence must include current visual bible",
            "review-ready take must bind current approved shot.json",
            "timeline approval evidence must include current source manifest",
        ):
            self.assertTrue(any(expected in message for message in messages), (expected, result))

    def test_superseded_lookdev_history_keeps_its_original_storyboard_evidence(self) -> None:
        from validate_project import _check_prerequisite_evidence_chain

        story_path = self.root / "01_story" / "STORY_CONTRACT.md"
        current_board_path = self.root / "02_storyboard" / "storyboard.json"
        historical_board_path = self.root / "02_storyboard" / "records" / "v001" / "storyboard.json"
        look_path = self.root / "03_lookdev" / "VISUAL_BIBLE.md"
        for path, content in (
            (story_path, b"story"),
            (current_board_path, b'{"storyboard_id":"current_board"}'),
            (historical_board_path, b'{"storyboard_id":"old_board"}'),
            (look_path, b"same-lookdev-bytes"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        historical_board_hash = hashlib.sha256(historical_board_path.read_bytes()).hexdigest()
        approval_path = self.root / "09_approvals" / "APR_LOOKDEV_0001.json"
        historical_approval = {
            "project_id": "take-me",
            "approval_id": "APR_LOOKDEV_0001",
            "subject_type": "LOOKDEV",
            "subject_id": "visual-bible",
            "gate": "LOOKDEV",
            "review_status": "USER_APPROVED",
            "superseded_by_approval_id": "APR_LOOKDEV_0002",
            "evidence": [
                {
                    "path": historical_board_path.relative_to(self.root).as_posix(),
                    "sha256": historical_board_hash,
                }
            ],
        }
        write_json(approval_path, historical_approval)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["storyboards"] = [
            (
                {
                    "project_id": "take-me",
                    "storyboard_id": "current_board",
                    "review_status": "DRAFT",
                },
                current_board_path,
            )
        ]
        records["approvals"] = [(historical_approval, approval_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "story_contract": story_path.relative_to(self.root).as_posix(),
                "storyboard": current_board_path.relative_to(self.root).as_posix(),
                "visual_bible": look_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []

        _check_prerequisite_evidence_chain(self.root, project, records, errors)

        self.assertFalse(
            any(
                "lookdev approval evidence must include current storyboard"
                in item["message"].lower()
                for item in errors
            ),
            errors,
        )

    def test_fixed_authority_approvals_require_complete_immutable_archive_evidence(self) -> None:
        from validate_project import _check_fixed_approval_archives

        cases = (
            (
                "STORY",
                "story-contract",
                self.root / "01_story" / "STORY_CONTRACT.md",
                self.root / "01_story" / "history" / "story-contract" / "v001" / "STORY_CONTRACT.md",
            ),
            (
                "STORYBOARD",
                "take_me_board",
                self.root / "02_storyboard" / "storyboard.json",
                self.root / "02_storyboard" / "history" / "take_me_board" / "v001" / "storyboard.json",
            ),
            (
                "LOOKDEV",
                "visual-bible",
                self.root / "03_lookdev" / "VISUAL_BIBLE.md",
                self.root / "03_lookdev" / "history" / "visual-bible" / "v001" / "VISUAL_BIBLE.md",
            ),
            (
                "SHOT_STILL",
                "S01_SH001",
                self.root / "05_shots" / "S01_SH001" / "shot.json",
                self.root / "05_shots" / "S01_SH001" / "history" / "v001" / "shot.json",
            ),
            (
                "SOURCE_LIBRARY",
                "source_main",
                self.root / "06_source_library" / "source_manifest.json",
                self.root / "06_source_library" / "history" / "source_main" / "v001" / "source_manifest.json",
            ),
        )
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        for index, (subject_type, subject_id, current_path, archive_path) in enumerate(cases, start=1):
            current_path.parent.mkdir(parents=True, exist_ok=True)
            current_path.write_bytes(f"{subject_type}-approved-bytes".encode("ascii"))
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_bytes(current_path.read_bytes())
            digest = hashlib.sha256(current_path.read_bytes()).hexdigest()
            approval_id = f"APR_{subject_type}_{index:04d}"
            approval_path = self.root / "09_approvals" / f"{approval_id}.json"
            approval = {
                "project_id": "take-me",
                "approval_id": approval_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "gate": subject_type,
                "subject_sha256": digest,
                "review_status": "USER_APPROVED",
                "supersedes_approval_id": None,
                "superseded_by_approval_id": None,
                "evidence": [
                    {"path": current_path.relative_to(self.root).as_posix(), "sha256": digest},
                    {"path": archive_path.relative_to(self.root).as_posix(), "sha256": digest},
                ],
            }
            write_json(approval_path, approval)
            records["approvals"].append((approval, approval_path))

        board_panel = self.root / "02_storyboard" / "panels" / "S01_P001.png"
        archived_board_panel = (
            self.root
            / "02_storyboard"
            / "history"
            / "take_me_board"
            / "v001"
            / "evidence"
            / "02_storyboard"
            / "panels"
            / "S01_P001.png"
        )
        board_panel.parent.mkdir(parents=True, exist_ok=True)
        archived_board_panel.parent.mkdir(parents=True, exist_ok=True)
        board_panel.write_bytes(b"visible-panel")
        archived_board_panel.write_bytes(board_panel.read_bytes())
        panel_hash = hashlib.sha256(board_panel.read_bytes()).hexdigest()
        records["approvals"][1][0]["evidence"].extend(
            [
                {"path": board_panel.relative_to(self.root).as_posix(), "sha256": panel_hash},
                {"path": archived_board_panel.relative_to(self.root).as_posix(), "sha256": panel_hash},
            ]
        )

        errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, errors)
        self.assertEqual([], errors)

        source_approval = records["approvals"][4][0]
        source_evidence = [dict(item) for item in source_approval["evidence"]]
        source_approval["evidence"] = source_approval["evidence"][:1]
        source_archive_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, source_archive_errors)
        self.assertTrue(
            any(
                item["code"] == "ARCHIVE_EVIDENCE_MISSING"
                and "SOURCE_LIBRARY" in item["message"]
                for item in source_archive_errors
            ),
            source_archive_errors,
        )
        source_approval["evidence"] = source_evidence

        board_approval = records["approvals"][1][0]
        board_approval["evidence"] = board_approval["evidence"][:1]
        missing_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, missing_errors)
        self.assertTrue(
            any(
                item["code"] == "ARCHIVE_EVIDENCE_MISSING"
                and "STORYBOARD" in item["message"]
                for item in missing_errors
            ),
            missing_errors,
        )

        board_approval["evidence"] = [
            {
                "path": cases[1][2].relative_to(self.root).as_posix(),
                "sha256": board_approval["subject_sha256"],
            },
            {
                "path": cases[1][3].relative_to(self.root).as_posix(),
                "sha256": board_approval["subject_sha256"],
            },
        ]
        story_current, story_archive = cases[0][2], cases[0][3]
        story_archive.unlink()
        os.link(story_current, story_archive)
        alias_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, alias_errors)
        self.assertTrue(
            any(item["code"] == "ARCHIVE_ALIAS_UNSAFE" for item in alias_errors),
            alias_errors,
        )

        story_archive.unlink()
        noncanonical_story_archive = story_archive.parent / "evidence" / "story-copy.md"
        noncanonical_story_archive.parent.mkdir(parents=True, exist_ok=True)
        noncanonical_story_archive.write_bytes(story_current.read_bytes())
        story_approval = records["approvals"][0][0]
        story_approval["evidence"][1]["path"] = noncanonical_story_archive.relative_to(self.root).as_posix()
        noncanonical_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, noncanonical_errors)
        self.assertTrue(
            any(
                item["code"] == "ARCHIVE_EVIDENCE_MISSING"
                and "canonical" in item["message"].lower()
                for item in noncanonical_errors
            ),
            noncanonical_errors,
        )

        story_archive.write_bytes(story_current.read_bytes())
        story_approval["evidence"][1]["path"] = story_archive.relative_to(self.root).as_posix()
        second_story_approval = {
            **story_approval,
            "approval_id": "APR_STORY_0099",
            "evidence": [dict(item) for item in story_approval["evidence"]],
        }
        second_story_path = self.root / "09_approvals" / "APR_STORY_0099.json"
        records["approvals"].append((second_story_approval, second_story_path))
        reused_version_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, reused_version_errors)
        self.assertTrue(
            any(item["code"] == "ARCHIVE_VERSION_REUSED" for item in reused_version_errors),
            reused_version_errors,
        )

    def test_superseded_legacy_fixed_approval_can_use_a_filesystem_archive_without_rewriting_evidence(self) -> None:
        from validate_project import _check_fixed_approval_archives

        current = self.root / "01_story" / "STORY_CONTRACT.md"
        archive = self.root / "01_story" / "history" / "story-contract" / "v001" / "STORY_CONTRACT.md"
        current.parent.mkdir(parents=True, exist_ok=True)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"old-approved-story")
        old_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        current.write_bytes(b"new-draft-story")
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_STORY_0001",
            "subject_type": "STORY",
            "subject_id": "story-contract",
            "gate": "STORY",
            "subject_sha256": old_hash,
            "review_status": "SUPERSEDED",
            "supersedes_approval_id": None,
            "superseded_by_approval_id": "APR_STORY_0002",
            # Immutable legacy evidence remains untouched and names the once-current path.
            "evidence": [
                {"path": current.relative_to(self.root).as_posix(), "sha256": old_hash}
            ],
        }
        records = {key: [] for key in ("assets", "shots", "takes", "approvals", "sources", "source_manifests", "storyboards", "timelines", "deliveries")}
        records["approvals"] = [(approval, self.root / "09_approvals" / "APR_STORY_0001.json")]
        errors: list[dict] = []

        _check_fixed_approval_archives(self.root, records, errors)

        self.assertEqual([], errors)

        approval["review_status"] = "REJECTED"
        rejected_history_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, rejected_history_errors)
        self.assertEqual([], rejected_history_errors)

        approval["superseded_by_approval_id"] = None
        current_rejected_errors: list[dict] = []
        _check_fixed_approval_archives(self.root, records, current_rejected_errors)
        self.assertTrue(
            any(item["code"] == "ARCHIVE_VERSION_INVALID" for item in current_rejected_errors),
            current_rejected_errors,
        )

    def test_archive_reparse_check_allows_onedrive_cloud_tags_but_rejects_name_redirection(self) -> None:
        from validate_project import _is_name_redirecting_reparse

        cloud_metadata = type(
            "CloudMetadata",
            (),
            {"st_mode": 0o100000, "st_reparse_tag": 0x9000001A},
        )()
        junction_metadata = type(
            "JunctionMetadata",
            (),
            {"st_mode": 0o100000, "st_reparse_tag": 0xA0000003},
        )()
        with patch("validate_project.os.lstat", return_value=cloud_metadata):
            self.assertFalse(_is_name_redirecting_reparse(Path("cloud-placeholder")))
        with patch("validate_project.os.lstat", return_value=junction_metadata):
            self.assertTrue(_is_name_redirecting_reparse(Path("junction")))

    def test_user_review_required_approval_is_already_bound_to_current_subject_bytes(self) -> None:
        from validate_project import _check_approval_mapping

        story_path = self.root / "01_story" / "STORY_CONTRACT.md"
        story_path.parent.mkdir(parents=True, exist_ok=True)
        story_path.write_bytes(b"candidate-shown-to-user")
        actual_hash = hashlib.sha256(story_path.read_bytes()).hexdigest()
        approval_path = self.root / "09_approvals" / "APR_STORY_0001.json"
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_STORY_0001",
            "subject_type": "STORY",
            "subject_id": "story-contract",
            "gate": "STORY",
            "subject_sha256": "0" * 64,
            "review_status": "USER_REVIEW_REQUIRED",
            "evidence": [
                {
                    "path": story_path.relative_to(self.root).as_posix(),
                    "sha256": "0" * 64,
                }
            ],
        }
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["approvals"] = [(approval, approval_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "story_contract": story_path.relative_to(self.root).as_posix(),
            },
        }
        stale_errors: list[dict] = []

        _check_approval_mapping(self.root, project, records, stale_errors)

        self.assertIn("E_APPROVAL_HASH_MISMATCH", {item["code"] for item in stale_errors})

        approval["subject_sha256"] = actual_hash
        approval["evidence"][0]["sha256"] = actual_hash
        current_errors: list[dict] = []
        _check_approval_mapping(self.root, project, records, current_errors)
        self.assertEqual([], current_errors)

    def test_fixed_authority_archive_rejects_symlink_evidence(self) -> None:
        from validate_project import _check_fixed_approval_archives

        current = self.root / "01_story" / "STORY_CONTRACT.md"
        archive = self.root / "01_story" / "history" / "story-contract" / "v001" / "STORY_CONTRACT.md"
        current.parent.mkdir(parents=True, exist_ok=True)
        archive.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(b"approved-story")
        try:
            archive.symlink_to(current)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        digest = hashlib.sha256(current.read_bytes()).hexdigest()
        approval = {
            "project_id": "take-me",
            "approval_id": "APR_STORY_0001",
            "subject_type": "STORY",
            "subject_id": "story-contract",
            "gate": "STORY",
            "subject_sha256": digest,
            "review_status": "USER_APPROVED",
            "evidence": [
                {"path": current.relative_to(self.root).as_posix(), "sha256": digest},
                {"path": archive.relative_to(self.root).as_posix(), "sha256": digest},
            ],
        }
        records = {key: [] for key in ("assets", "shots", "takes", "approvals", "sources", "source_manifests", "storyboards", "timelines", "deliveries")}
        records["approvals"] = [(approval, self.root / "09_approvals" / "APR_STORY_0001.json")]
        errors: list[dict] = []

        _check_fixed_approval_archives(self.root, records, errors)

        self.assertTrue(any(item["code"] == "ARCHIVE_ALIAS_UNSAFE" for item in errors), errors)

    def test_approval_replacement_graph_is_reciprocal_same_subject_and_acyclic(self) -> None:
        from validate_project import _check_approval_replacement_graph

        old = {
            "project_id": "take-me",
            "approval_id": "APR_STORY_0001",
            "subject_type": "STORY",
            "subject_id": "story-contract",
            "gate": "STORY",
            "review_status": "SUPERSEDED",
            "supersedes_approval_id": None,
            "superseded_by_approval_id": "APR_STORY_0002",
        }
        successor = {
            **old,
            "approval_id": "APR_STORY_0002",
            "review_status": "DRAFT",
            "supersedes_approval_id": "APR_STORY_0001",
            "superseded_by_approval_id": None,
        }
        records = {key: [] for key in ("assets", "shots", "takes", "approvals", "sources", "source_manifests", "storyboards", "timelines", "deliveries")}
        records["approvals"] = [
            (old, self.root / "09_approvals" / "APR_STORY_0001.json"),
            (successor, self.root / "09_approvals" / "APR_STORY_0002.json"),
        ]
        errors: list[dict] = []
        _check_approval_replacement_graph(self.root, records, errors)
        self.assertEqual([], errors)

        old["review_status"] = "REJECTED"
        rejected_history_errors: list[dict] = []
        _check_approval_replacement_graph(self.root, records, rejected_history_errors)
        self.assertEqual([], rejected_history_errors)
        old["review_status"] = "SUPERSEDED"

        old["subject_type"] = "SHOT_STILL"
        old["subject_id"] = "S01_SH001"
        old["gate"] = "SHOT_STILL"
        old["review_status"] = "USER_APPROVED"
        successor["subject_type"] = "SHOT_STILL"
        successor["subject_id"] = "S01_SH001"
        successor["gate"] = "SHOT_STILL"
        replaced_shot_errors: list[dict] = []
        _check_approval_replacement_graph(self.root, records, replaced_shot_errors)
        self.assertTrue(
            any(
                item["code"] == "APPROVAL_CHAIN_INVALID"
                and "superseded status" in item["message"].lower()
                for item in replaced_shot_errors
            ),
            replaced_shot_errors,
        )
        old["subject_type"] = "STORY"
        old["subject_id"] = "story-contract"
        old["gate"] = "STORY"
        old["review_status"] = "SUPERSEDED"
        successor["subject_type"] = "STORY"
        successor["subject_id"] = "story-contract"
        successor["gate"] = "STORY"

        successor["project_id"] = "other-project"
        cross_project_errors: list[dict] = []
        _check_approval_replacement_graph(self.root, records, cross_project_errors)
        self.assertTrue(
            any(item["code"] == "APPROVAL_CHAIN_INVALID" for item in cross_project_errors),
            cross_project_errors,
        )

        successor["project_id"] = "take-me"
        old["supersedes_approval_id"] = "APR_STORY_0002"
        successor["superseded_by_approval_id"] = "APR_STORY_0001"
        cycle_errors: list[dict] = []
        _check_approval_replacement_graph(self.root, records, cycle_errors)
        self.assertTrue(
            any(
                item["code"] == "APPROVAL_CHAIN_INVALID"
                and "cycle" in item["message"].lower()
                for item in cycle_errors
            ),
            cycle_errors,
        )

    def test_historical_locked_timeline_uses_its_preserved_clip_hash_not_current_source_membership(self) -> None:
        from validate_project import _check_source_and_timeline

        old_source = self.root / "06_source_library" / "approved_video" / "old.mov"
        old_source.parent.mkdir(parents=True, exist_ok=True)
        old_source.write_bytes(b"preserved-old-source")
        old_hash = hashlib.sha256(old_source.read_bytes()).hexdigest()
        timeline_v1_path = self.root / "07_edit" / "timeline.json"
        timeline_v2_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        timeline_v1 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "lock_status": "PICTURE_LOCKED",
            "review_status": "USER_APPROVED",
            "tracks": [{"track_id": "TRK_V1", "order": 1}],
            "events": [],
            "clips": [
                {
                    "clip_id": "CLIP_OLD",
                    "track_id": "TRK_V1",
                    "source_id": "SRC_OLD",
                    "source_file": old_source.relative_to(self.root).as_posix(),
                    "source_sha256": old_hash,
                    "source_in_frame": 0,
                    "source_out_frame": 24,
                    "timeline_in_frame": 0,
                    "timeline_out_frame": 24,
                    "review_status": "USER_APPROVED",
                }
            ],
        }
        timeline_v2 = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 2,
            "lock_status": "UNLOCKED",
            "review_status": "DRAFT",
            "tracks": [],
            "events": [],
            "clips": [],
        }
        write_json(timeline_v1_path, timeline_v1)
        write_json(timeline_v2_path, timeline_v2)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["sources"] = [
            (
                {
                    "source_id": "SRC_CURRENT",
                    "take_id": "S01_SH001_T01",
                    "path": "current.mov",
                    "sha256": "f" * 64,
                    "source_status": "SOURCE_APPROVED",
                },
                self.root / "06_source_library" / "source_manifest.json",
            )
        ]
        records["timelines"] = [(timeline_v1, timeline_v1_path), (timeline_v2, timeline_v2_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "timeline": timeline_v2_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []

        _check_source_and_timeline(self.root, project, records, errors)

        historical_errors = [
            item
            for item in errors
            if item.get("path") == timeline_v1_path.relative_to(self.root).as_posix()
        ]
        self.assertFalse(
            any(item["code"] in {"UNKNOWN_SOURCE", "E_UNAPPROVED_INPUT"} for item in historical_errors),
            errors,
        )

        old_source.write_bytes(b"mutated-after-lock")
        tampered_errors: list[dict] = []
        _check_source_and_timeline(self.root, project, records, tampered_errors)
        self.assertTrue(
            any(
                item["code"] == "E_APPROVAL_HASH_MISMATCH"
                and item.get("path") == timeline_v1_path.relative_to(self.root).as_posix()
                for item in tampered_errors
            ),
            tampered_errors,
        )

    def test_current_timeline_cannot_bypass_locked_source_library_with_a_take_id(self) -> None:
        from validate_project import _check_source_and_timeline

        take_output = self.root / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "source.mov"
        take_output.parent.mkdir(parents=True, exist_ok=True)
        take_output.write_bytes(b"approved-but-not-in-source-library")
        output_hash = hashlib.sha256(take_output.read_bytes()).hexdigest()
        take = {
            "project_id": "take-me",
            "take_id": "S01_SH001_T01",
            "review_status": "USER_APPROVED",
            "source_status": "SOURCE_APPROVED",
            "output_file": take_output.relative_to(self.root).as_posix(),
            "output_sha256": output_hash,
        }
        timeline_path = self.root / "07_edit" / "timeline.json"
        timeline = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 1,
            "review_status": "USER_APPROVED",
            "lock_status": "PICTURE_LOCKED",
            "tracks": [{"track_id": "TRK_V1", "order": 1}],
            "events": [],
            "clips": [
                {
                    "clip_id": "CLIP_BYPASS",
                    "track_id": "TRK_V1",
                    "source_id": take["take_id"],
                    "source_file": take["output_file"],
                    "source_sha256": output_hash,
                    "source_in_frame": 0,
                    "source_out_frame": 24,
                    "timeline_in_frame": 0,
                    "timeline_out_frame": 24,
                    "review_status": "USER_APPROVED",
                }
            ],
        }
        write_json(timeline_path, timeline)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["takes"] = [(take, take_output.parent / "take.json")]
        records["timelines"] = [(timeline, timeline_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {"timeline": timeline_path.relative_to(self.root).as_posix()},
        }
        errors: list[dict] = []

        _check_source_and_timeline(self.root, project, records, errors)

        self.assertTrue(
            any(item["code"] in {"UNKNOWN_SOURCE", "E_UNAPPROVED_INPUT"} for item in errors),
            errors,
        )

    def test_historical_reviewed_delivery_requires_an_exact_approved_locked_timeline(self) -> None:
        from validate_project import _check_deliveries

        current_timeline_path = self.root / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        current_timeline = {
            "project_id": "take-me",
            "timeline_id": "main_timeline",
            "version": 2,
            "review_status": "USER_APPROVED",
            "lock_status": "PICTURE_LOCKED",
        }
        write_json(current_timeline_path, current_timeline)
        arbitrary_source = self.root / "misc" / "not-a-timeline.bin"
        arbitrary_source.parent.mkdir(parents=True, exist_ok=True)
        arbitrary_source.write_bytes(b"self-consistent-but-not-a-timeline")
        arbitrary_hash = hashlib.sha256(arbitrary_source.read_bytes()).hexdigest()
        historical_delivery_path = self.root / "08_delivery" / "delivery.json"
        historical_delivery = {
            "project_id": "take-me",
            "delivery_id": "final_delivery",
            "version": 1,
            "supersedes_delivery": None,
            "review_status": "USER_APPROVED",
            "approval_id": "APR_FINISH_0001",
            "source_timeline": {
                "timeline_id": "main_timeline",
                "path": arbitrary_source.relative_to(self.root).as_posix(),
                "sha256": arbitrary_hash,
            },
            "export": {},
            "derivation": {
                "input_hashes": [
                    {
                        "path": arbitrary_source.relative_to(self.root).as_posix(),
                        "sha256": arbitrary_hash,
                    }
                ]
            },
            "qa": {},
        }
        write_json(historical_delivery_path, historical_delivery)
        historical_delivery_hash = hashlib.sha256(historical_delivery_path.read_bytes()).hexdigest()
        finish_approval_path = self.root / "09_approvals" / "APR_FINISH_0001.json"
        finish_approval = {
            "project_id": "take-me",
            "approval_id": "APR_FINISH_0001",
            "subject_type": "DELIVERY",
            "subject_id": "final_delivery",
            "subject_sha256": historical_delivery_hash,
            "gate": "FINISH",
            "review_status": "USER_APPROVED",
            "superseded_by_approval_id": "APR_FINISH_0002",
            "evidence": [
                {
                    "path": historical_delivery_path.relative_to(self.root).as_posix(),
                    "sha256": historical_delivery_hash,
                    "verified_claim": "preserved historical delivery",
                }
            ],
        }
        write_json(finish_approval_path, finish_approval)
        current_delivery_path = self.root / "08_delivery" / "records" / "final_delivery" / "v002" / "delivery.json"
        current_delivery = {
            **historical_delivery,
            "version": 2,
            "review_status": "DRAFT",
            "approval_id": None,
            "source_timeline": {
                "timeline_id": "main_timeline",
                "path": current_timeline_path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(current_timeline_path.read_bytes()).hexdigest(),
            },
            "supersedes_delivery": {
                "delivery_id": "final_delivery",
                "version": 1,
                "path": historical_delivery_path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(historical_delivery_path.read_bytes()).hexdigest(),
                "approval_id": "APR_FINISH_0001",
            },
        }
        write_json(current_delivery_path, current_delivery)
        records = {
            key: []
            for key in (
                "assets", "shots", "takes", "approvals", "sources", "source_manifests",
                "storyboards", "timelines", "deliveries",
            )
        }
        records["timelines"] = [(current_timeline, current_timeline_path)]
        records["deliveries"] = [
            (historical_delivery, historical_delivery_path),
            (current_delivery, current_delivery_path),
        ]
        records["approvals"] = [(finish_approval, finish_approval_path)]
        project = {
            "project_id": "take-me",
            "authority_files": {
                "timeline": current_timeline_path.relative_to(self.root).as_posix(),
                "delivery_record": current_delivery_path.relative_to(self.root).as_posix(),
            },
        }
        errors: list[dict] = []
        with patch("validate_project.inspect_media", return_value={"ok": False, "errors": []}):
            _check_deliveries(self.root, project, records, errors)

        historical_location = historical_delivery_path.relative_to(self.root).as_posix()
        self.assertTrue(
            any(
                item["code"] == "E_STAGE_PREREQ"
                and item.get("path") == historical_location
                and "timeline" in item["message"].lower()
                for item in errors
            ),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
