import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ValidateProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "take-me"
        self.project.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_valid_records(self) -> None:
        write_json(
            self.project / "project.json",
            {
                "schema_version": "2.0.0",
                "schema_id": "cinema-studio-pipeline/project@2.0.0",
                "project_id": "take-me",
                "title": "TAKE ME",
                "execution_mode": "GUIDED",
                "production_mode": "RAW_SOURCE_FIRST",
                "review_status": "DRAFT",
                "stage_gates": {
                    "STORY": "DRAFT",
                    "STORYBOARD": "USER_REVIEW_REQUIRED",
                    "LOOKDEV": "DRAFT",
                },
            },
        )
        write_json(
            self.project / "04_assets" / "records" / "woman_seated" / "asset.json",
            {
                "schema_version": "2.0.0",
                "schema_id": "cinema-studio-pipeline/asset@2.0.0",
                "project_id": "take-me",
                "asset_id": "woman_seated",
                "kind": "CHARACTER",
                "review_status": "DRAFT",
            },
        )
        write_json(
            self.project / "05_shots" / "S01_SH010" / "shot.json",
            {
                "schema_version": "2.0.0",
                "schema_id": "cinema-studio-pipeline/shot@2.0.0",
                "project_id": "take-me",
                "shot_id": "S01_SH010",
                "scene_id": "S01",
                "review_status": "DRAFT",
                "active_assets": [],
                "still_evidence": [],
            },
        )
        write_json(
            self.project
            / "05_shots"
            / "S01_SH010"
            / "takes"
            / "S01_SH010_T01"
            / "take.json",
            {
                "schema_version": "2.0.0",
                "schema_id": "cinema-studio-pipeline/take@2.0.0",
                "project_id": "take-me",
                "take_id": "S01_SH010_T01",
                "shot_id": "S01_SH010",
                "model": {
                    "provider": "HIGGSFIELD",
                    "name": "Seedance",
                    "verified": True,
                },
                "prompt_version": 1,
                "output_file": "take_01.mp4",
                "review_status": "DRAFT",
            },
        )

    def test_validates_schema_and_cross_record_references(self) -> None:
        self._write_valid_records()
        schema_dir = self.project / "schemas"
        write_json(
            schema_dir / "project.schema.json",
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["schema_version", "project_id"],
                "properties": {
                    "schema_version": {"const": "2.0.0"},
                    "project_id": {
                        "type": "string",
                        "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                    },
                },
            },
        )
        for schema_name in ("asset", "shot", "storyboard", "take", "approval", "source-library", "timeline", "delivery"):
            write_json(
                schema_dir / f"{schema_name}.schema.json",
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                },
            )

        from validate_project import validate_project

        result = validate_project(self.project, schema_dir=schema_dir)

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["errors"])
        self.assertIn("project.json", result["checked_files"])

    def test_reports_unknown_assets_takes_and_out_of_order_approved_stages(self) -> None:
        self._write_valid_records()
        project_data = json.loads(
            (self.project / "project.json").read_text(encoding="utf-8")
        )
        project_data["stage_gates"] = {
            "STORY": "USER_APPROVED",
            "STORYBOARD": "DRAFT",
            "LOOKDEV": "USER_APPROVED",
        }
        write_json(self.project / "project.json", project_data)
        shot_path = self.project / "05_shots" / "S01_SH010" / "shot.json"
        shot = json.loads(shot_path.read_text(encoding="utf-8"))
        shot["active_assets"] = [{"asset_id": "missing_character", "role": "IDENTITY"}]
        write_json(shot_path, shot)
        take_path = (
            self.project
            / "05_shots"
            / "S01_SH010"
            / "takes"
            / "S01_SH010_T01"
            / "take.json"
        )
        take = json.loads(take_path.read_text(encoding="utf-8"))
        take["shot_id"] = "S99_SH999"
        write_json(take_path, take)

        from validate_project import validate_project

        result = validate_project(self.project)
        codes = {issue["code"] for issue in result["errors"]}

        self.assertFalse(result["ok"])
        self.assertIn("UNKNOWN_ASSET", codes)
        self.assertIn("UNKNOWN_SHOT", codes)
        self.assertIn("STAGE_ORDER", codes)

    def test_central_take_review_requires_output_and_record_json_evidence(self) -> None:
        self._write_valid_records()
        take_path = (
            self.project
            / "05_shots"
            / "S01_SH010"
            / "takes"
            / "S01_SH010_T01"
            / "take.json"
        )
        take = json.loads(take_path.read_text(encoding="utf-8"))
        output_path = take_path.parent / "take_01.mp4"
        output_path.write_bytes(b"approved-take")
        import hashlib
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        take["output_file"] = str(output_path.relative_to(self.project)).replace("\\", "/")
        take["output_sha256"] = digest
        write_json(take_path, take)

        approval_path = self.project / "09_approvals" / "APR_S01_SH010_T01_0001.json"
        approval = {
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "approval_id": "APR_S01_SH010_T01_0001",
                "subject_type": "TAKE",
                "subject_id": "S01_SH010_T01",
                "subject_sha256": digest,
                "gate": "RAW_VIDEO",
                "review_status": "USER_APPROVED",
                "decided_by_type": "USER",
                "decided_by": "project-owner",
                "decided_at": "2026-08-11T00:00:00Z",
                "user_evidence_reference": "chat-approval-1",
                "evidence": [{"path": take["output_file"], "sha256": digest, "verified_claim": "approved take"}],
            }
        write_json(approval_path, approval)

        from validate_project import validate_project

        rejected = validate_project(self.project)
        self.assertTrue(
            any(
                issue["code"] == "E_APPROVAL_HASH_MISMATCH"
                and "record json" in issue["message"].lower()
                for issue in rejected["errors"]
            ),
            rejected,
        )

        record_digest = hashlib.sha256(take_path.read_bytes()).hexdigest()
        approval["evidence"].append(
            {
                "path": take_path.relative_to(self.project).as_posix(),
                "sha256": record_digest,
                "verified_claim": "immutable take record",
            }
        )
        write_json(approval_path, approval)
        accepted = validate_project(self.project)
        self.assertFalse(
            any("record json" in issue["message"].lower() for issue in accepted["errors"]),
            accepted,
        )

    def test_malformed_json_is_reported_without_a_traceback(self) -> None:
        (self.project / "project.json").write_text("{not-json", encoding="utf-8")

        from validate_project import validate_project

        result = validate_project(self.project)

        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_JSON", result["errors"][0]["code"])

    def test_valid_json_non_object_and_idless_approval_records_are_not_dropped(self) -> None:
        self._write_valid_records()
        approvals = self.project / "09_approvals"
        approvals.mkdir(parents=True, exist_ok=True)
        (approvals / "scalar.json").write_text("[]", encoding="utf-8")
        write_json(
            approvals / "missing-id.json",
            {
                "schema_id": "cinema-studio-pipeline/approval@2.0.0",
                "schema_version": "2.0.0",
                "project_id": "take-me",
            },
        )
        empty_schemas = self.project / "empty-schemas"
        empty_schemas.mkdir()

        from validate_project import validate_project

        result = validate_project(self.project, schema_dir=empty_schemas)

        invalid = [item for item in result["errors"] if item["code"] == "INVALID_RECORD"]
        self.assertGreaterEqual(len(invalid), 2, result)
        self.assertTrue(any(item.get("path", "").endswith("scalar.json") for item in invalid))
        self.assertTrue(any(item.get("path", "").endswith("missing-id.json") for item in invalid))

    def test_canonical_historical_records_with_wrong_schema_ids_are_validated(self) -> None:
        self._write_valid_records()
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
                "schema_id": "wrong/timeline@2.0.0",
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 2,
            },
        )
        historical_delivery = (
            self.project
            / "08_delivery"
            / "records"
            / "final_delivery"
            / "v002"
            / "delivery.json"
        )
        write_json(
            historical_delivery,
            {
                "schema_id": "wrong/delivery@2.0.0",
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "delivery_id": "final_delivery",
                "version": 2,
            },
        )
        seed_timeline = self.project / "07_edit" / "timeline.json"
        seed_delivery = self.project / "08_delivery" / "delivery.json"
        write_json(seed_timeline, {"schema_id": "wrong/timeline@2.0.0"})
        write_json(seed_delivery, {"schema_id": "wrong/delivery@2.0.0"})
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"] = {
            "timeline": historical.relative_to(self.project).as_posix(),
            "delivery_record": historical_delivery.relative_to(self.project).as_posix(),
        }
        write_json(project_path, project)
        empty_schemas = self.project / "empty-schemas"
        empty_schemas.mkdir()

        from validate_project import validate_project

        result = validate_project(self.project, schema_dir=empty_schemas)

        self.assertIn("SCHEMA_ID_MISMATCH", {item["code"] for item in result["errors"]})
        self.assertIn(historical.relative_to(self.project).as_posix(), result["checked_files"])
        self.assertIn(
            historical_delivery.relative_to(self.project).as_posix(),
            result["checked_files"],
        )
        self.assertIn(seed_timeline.relative_to(self.project).as_posix(), result["checked_files"])
        self.assertIn(seed_delivery.relative_to(self.project).as_posix(), result["checked_files"])

    def test_declared_authority_targets_must_exist_even_while_draft(self) -> None:
        self._write_valid_records()
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8"))
        project["authority_files"] = {
            "timeline": "07_edit/timeline.json",
            "asset_records_root": "04_assets/records",
        }
        write_json(project_path, project)
        empty_schemas = self.project / "empty-schemas"
        empty_schemas.mkdir()

        from validate_project import validate_project

        result = validate_project(self.project, schema_dir=empty_schemas)

        missing = [item for item in result["errors"] if item["code"] == "AUTHORITY_TARGET_MISSING"]
        self.assertTrue(any(item.get("path") == "07_edit/timeline.json" for item in missing), result)


if __name__ == "__main__":
    unittest.main()
