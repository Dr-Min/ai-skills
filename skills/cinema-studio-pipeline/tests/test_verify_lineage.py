import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class VerifyLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.master = self.project / "04_assets" / "characters" / "woman_master.png"
        self.patch = self.project / "04_assets" / "characters" / "woman_wet.png"
        self.master.parent.mkdir(parents=True)
        self.master.write_bytes(b"immutable-master")
        self.patch.write_bytes(b"independent-patch")
        self.master_record = self.project / "04_assets" / "records" / "woman_master" / "asset.json"
        self.wet_record = self.project / "04_assets" / "records" / "woman_wet" / "asset.json"
        write_json(self.project / "project.json", {"authority_files": {"asset_records_root": "04_assets/records"}, "paths": {"shots": "05_shots"}})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_manifest(self) -> None:
        write_json(
            self.master_record,
            {
                        "asset_id": "woman_master",
                        "files": {
                            "immutable_master": {
                                "path": "04_assets/characters/woman_master.png",
                                "sha256": sha256(self.master),
                            }
                        },
                        "review_status": "USER_APPROVED",
                        "approval_id": "APR_WOMAN_MASTER_0001",
                        "immutable": True,
                        "lineage": {
                            "immutable_master_asset_id": None,
                            "parent_asset_id": None,
                            "source_files": [],
                            "derivation": "IMPORTED",
                            "input_hashes": [],
                            "output_sha256": sha256(self.master),
                        },
            },
        )
        write_json(
            self.wet_record,
            {
                        "asset_id": "woman_wet",
                        "files": {
                            "immutable_master": {
                                "path": "04_assets/characters/woman_wet.png",
                                "sha256": sha256(self.patch),
                            }
                        },
                        "review_status": "INTERNAL_REVIEW",
                        "lineage": {
                            "immutable_master_asset_id": "woman_master",
                            "parent_asset_id": "woman_master",
                            "source_files": [
                                "04_assets/characters/woman_master.png"
                            ],
                            "derivation": "PATCH_FROM_MASTER",
                            "input_hashes": [
                                {
                                    "path": "04_assets/characters/woman_master.png",
                                    "sha256": sha256(self.master),
                                }
                            ],
                            "output_sha256": sha256(self.patch),
                        },
            },
        )

    def test_accepts_distinct_outputs_with_verified_parent_hashes(self) -> None:
        self._write_manifest()

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertTrue(result["ok"], result)
        self.assertEqual(2, result["records_checked"])

    def test_detects_modified_approved_master(self) -> None:
        self._write_manifest()
        self.master.write_bytes(b"changed-after-approval")

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn(
            "E_APPROVAL_HASH_MISMATCH",
            {item["code"] for item in result["errors"]},
        )

    def test_rejects_derivative_as_patch_base_and_parent_path_overwrite(self) -> None:
        self._write_manifest()
        derivative = json.loads(self.wet_record.read_text(encoding="utf-8"))
        derivative["lineage"]["parent_asset_id"] = "woman_intermediate"
        derivative["files"]["immutable_master"] = {
            "path": "04_assets/characters/woman_wet.png",
            "sha256": sha256(self.patch),
        }
        derivative["lineage"]["output_sha256"] = sha256(self.patch)
        write_json(self.wet_record, derivative)
        write_json(
            self.project / "04_assets" / "records" / "woman_intermediate" / "asset.json",
            {
                "asset_id": "woman_intermediate",
                "files": {
                    "immutable_master": {
                        "path": "04_assets/characters/woman_wet.png",
                        "sha256": sha256(self.patch),
                    }
                },
                "review_status": "INTERNAL_REVIEW",
                "lineage": {
                    "immutable_master_asset_id": "woman_master",
                    "parent_asset_id": "woman_master",
                    "derivation": "CROP_FROM_MASTER",
                    "input_hashes": [],
                    "source_files": [],
                    "output_sha256": sha256(self.patch),
                },
            },
        )

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_DERIVATIVE_AS_EDIT_BASE", codes)
        self.assertIn("LINEAGE_OVERWRITE", codes)

    def test_reports_parent_cycles(self) -> None:
        self._write_manifest()
        master = json.loads(self.master_record.read_text(encoding="utf-8"))
        master["lineage"]["parent_asset_id"] = "woman_wet"
        write_json(self.master_record, master)

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn("LINEAGE_CYCLE", {item["code"] for item in result["errors"]})

    def test_rejects_media_paths_that_escape_the_project(self) -> None:
        self._write_manifest()
        master = json.loads(self.master_record.read_text(encoding="utf-8"))
        master["files"]["immutable_master"]["path"] = "../outside.png"
        write_json(self.master_record, master)

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn("PATH_ESCAPE", {item["code"] for item in result["errors"]})

    def test_patch_inputs_must_bind_to_declared_immutable_master(self) -> None:
        self._write_manifest()
        derivative = json.loads(self.wet_record.read_text(encoding="utf-8"))
        derivative["lineage"]["source_files"] = ["04_assets/characters/woman_wet.png"]
        derivative["lineage"]["input_hashes"] = [
            {
                "path": "04_assets/characters/woman_wet.png",
                "sha256": sha256(self.patch),
            }
        ]
        write_json(self.wet_record, derivative)

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn("E_DERIVATIVE_AS_EDIT_BASE", {item["code"] for item in result["errors"]})

    def test_take_input_must_bind_to_declared_parent_output_not_unrelated_file(self) -> None:
        parent_output = self.project / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T00" / "raw.mov"
        child_output = self.project / "05_shots" / "S01_SH001" / "takes" / "S01_SH001_T01" / "processed.mov"
        unrelated = self.project / "05_shots" / "unrelated.mov"
        parent_output.parent.mkdir(parents=True)
        child_output.parent.mkdir(parents=True)
        parent_output.write_bytes(b"authoritative-parent")
        child_output.write_bytes(b"derived-child")
        unrelated.write_bytes(b"self-consistent-but-unrelated")
        write_json(
            parent_output.parent / "take.json",
            {
                "take_id": "S01_SH001_T00",
                "review_status": "DRAFT",
                "output_file": parent_output.relative_to(self.project).as_posix(),
                "output_sha256": sha256(parent_output),
                "input_hashes": [],
                "lineage": {"parent_take_id": None, "source_take_ids": [], "source_asset_ids": [], "derivation": "GENERATED"},
            },
        )
        write_json(
            child_output.parent / "take.json",
            {
                "take_id": "S01_SH001_T01",
                "review_status": "INTERNAL_REVIEW",
                "output_file": child_output.relative_to(self.project).as_posix(),
                "output_sha256": sha256(child_output),
                "input_hashes": [{"path": unrelated.relative_to(self.project).as_posix(), "sha256": sha256(unrelated)}],
                "lineage": {"parent_take_id": "S01_SH001_T00", "source_take_ids": [], "source_asset_ids": [], "derivation": "TRANSCODE"},
            },
        )

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn("E_DERIVATIVE_AS_EDIT_BASE", {item["code"] for item in result["errors"]})

    def test_asset_parent_id_must_bind_to_authoritative_parent_bytes(self) -> None:
        self._write_manifest()
        derivative = json.loads(self.wet_record.read_text(encoding="utf-8"))
        derivative["lineage"]["derivation"] = "EXTRACTED_FRAME"
        derivative["lineage"]["source_files"] = ["04_assets/characters/woman_wet.png"]
        derivative["lineage"]["input_hashes"] = [
            {"path": "04_assets/characters/woman_wet.png", "sha256": sha256(self.patch)}
        ]
        write_json(self.wet_record, derivative)

        from verify_lineage import verify_lineage

        result = verify_lineage(self.project)
        self.assertIn("E_DERIVATIVE_AS_EDIT_BASE", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
