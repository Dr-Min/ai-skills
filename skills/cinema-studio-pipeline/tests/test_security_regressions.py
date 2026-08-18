import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _snapshot_project(self) -> None:
        shutil.copytree(SKILL_ROOT / "schemas", self.root / "00_schemas")
        project = json.loads((SKILL_ROOT / "templates" / "project.json").read_text(encoding="utf-8"))
        project["$schema"] = "00_schemas/project.schema.json"
        project["project_id"] = "security-test"
        project["project_prefix"] = "SEC"
        project["title"] = "Security test"
        project["notes"] = "Initialized security regression project."
        write_json(self.root / "project.json", project)

    def _override_schemas(self, dangerous_keyword: str) -> Path:
        schema_dir = self.root / "override-schemas"
        for name in (
            "project",
            "asset",
            "shot",
            "storyboard",
            "take",
            "approval",
            "source-library",
            "timeline",
            "delivery",
        ):
            schema = {"type": "object"}
            if name == "project":
                schema["allOf"] = [
                    {dangerous_keyword: "https://attacker.invalid/remote-schema"}
                ]
            write_json(schema_dir / f"{name}.schema.json", schema)
        write_json(
            self.root / "project.json",
            {
                "schema_id": "cinema-studio-pipeline/project@2.0.0",
                "schema_version": "2.0.0",
                "project_id": "security-test",
            },
        )
        return schema_dir

    def test_manifest_trust_failure_stops_before_project_schema_execution(self) -> None:
        self._snapshot_project()
        schema_path = self.root / "00_schemas" / "shot.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["allOf"] = [{"$dynamicRef": "https://attacker.invalid/remote-schema"}]
        write_json(schema_path, schema)

        from validate_project import validate_project

        with patch(
            "jsonschema.validators.validator_for",
            side_effect=AssertionError("untrusted project schema executed"),
        ) as validator_for:
            result = validate_project(self.root)

        self.assertFalse(result["ok"], result)
        self.assertFalse(validator_for.called, result)
        self.assertIn(
            "SCHEMA_SNAPSHOT_HASH_MISMATCH",
            {item["code"] for item in result["errors"]},
        )

    def test_manifest_bytes_mismatch_stops_before_any_schema_execution(self) -> None:
        self._snapshot_project()
        manifest_path = self.root / "00_schemas" / "schema-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["tampered"] = True
        write_json(manifest_path, manifest)

        from validate_project import validate_project

        with patch(
            "jsonschema.validators.validator_for",
            side_effect=AssertionError("schema executed after manifest trust failure"),
        ) as validator_for:
            result = validate_project(self.root)

        self.assertFalse(validator_for.called, result)
        self.assertIn(
            "SCHEMA_MANIFEST_MISMATCH",
            {item["code"] for item in result["errors"]},
        )

    def test_invalid_project_cannot_enable_untrusted_snapshot_schema_execution(self) -> None:
        shutil.copytree(SKILL_ROOT / "schemas", self.root / "00_schemas")
        (self.root / "project.json").write_text("[]", encoding="utf-8")
        write_json(
            self.root / "04_assets" / "records" / "hero" / "asset.json",
            {
                "schema_id": "cinema-studio-pipeline/asset@2.0.0",
                "asset_id": "hero",
            },
        )

        from validate_project import validate_project

        with patch(
            "jsonschema.validators.validator_for",
            side_effect=AssertionError("schema executed without trusted project"),
        ) as validator_for:
            result = validate_project(self.root)

        self.assertFalse(validator_for.called, result)
        self.assertIn("INVALID_PROJECT", {item["code"] for item in result["errors"]})

    def test_external_dynamic_and_recursive_schema_references_are_rejected_pre_execution(self) -> None:
        from validate_project import validate_project

        for keyword in ("$dynamicRef", "$recursiveRef"):
            with self.subTest(keyword=keyword):
                schema_dir = self._override_schemas(keyword)
                with patch(
                    "jsonschema.validators.validator_for",
                    side_effect=AssertionError("external schema reference executed"),
                ) as validator_for:
                    result = validate_project(self.root, schema_dir=schema_dir)
                self.assertFalse(validator_for.called, result)
                self.assertIn(
                    "INVALID_SCHEMA", {item["code"] for item in result["errors"]}
                )

    def test_validate_project_cli_rejects_deep_json_without_a_traceback(self) -> None:
        depth = 1200
        (self.root / "project.json").write_text(
            '{"x":' * depth + "null" + "}" * depth,
            encoding="utf-8",
        )

        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_DIR / "validate_project.py"), str(self.root), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(1, completed.returncode, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        result = json.loads(completed.stdout)
        self.assertIn("INVALID_JSON", {item["code"] for item in result["errors"]})

    def test_validate_project_cli_rejects_giant_integers_and_nonfinite_constants(self) -> None:
        invalid_documents = (
            '{"value":' + "9" * 5000 + "}",
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"value":-Infinity}',
            '{"value":1e9999}',
        )
        for document in invalid_documents:
            with self.subTest(prefix=document[:24]):
                (self.root / "project.json").write_text(document, encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(SCRIPTS_DIR / "validate_project.py"),
                        str(self.root),
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(1, completed.returncode, completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                result = json.loads(completed.stdout)
                self.assertIn(
                    "INVALID_JSON", {item["code"] for item in result["errors"]}
                )

    def test_long_approval_replacement_chain_is_checked_iteratively(self) -> None:
        write_json(
            self.root / "project.json",
            {
                "schema_version": "2.0.0",
                "project_id": "security-test",
                "paths": {"approvals": "09_approvals"},
            },
        )
        total = 1200
        for index in range(1, total + 1):
            approval_id = f"APR_CHAIN_{index:04d}"
            write_json(
                self.root / "09_approvals" / f"{approval_id}.json",
                {
                    "project_id": "security-test",
                    "approval_id": approval_id,
                    "subject_type": "ASSET",
                    "subject_id": "hero",
                    "gate": "ASSET_LOCK",
                    "review_status": "DRAFT",
                    "supersedes_approval_id": (
                        f"APR_CHAIN_{index + 1:04d}" if index < total else None
                    ),
                    "superseded_by_approval_id": (
                        f"APR_CHAIN_{index - 1:04d}" if index > 1 else None
                    ),
                },
            )
        empty_schemas = self.root / "empty-schemas"
        empty_schemas.mkdir()

        from validate_project import validate_project

        result = validate_project(self.root, schema_dir=empty_schemas)

        self.assertIsInstance(result, dict)
        self.assertFalse(
            any(
                item["code"] == "APPROVAL_CHAIN_INVALID"
                and "cycle" in item["message"].casefold()
                for item in result["errors"]
            ),
            result,
        )


if __name__ == "__main__":
    unittest.main()
