import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "init_project.ps1"
TEMPLATES = SKILL_ROOT / "templates"
MAX_INIT_INPUT_BYTES = 32 * 1024 * 1024


@unittest.skipIf(shutil.which("powershell") is None, "PowerShell is not available")
class InitProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name) / "달 프로젝트"
        self.receipt_store = Path(self.temp_dir.name) / "machine-state" / "receipts"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-File",
                str(SCRIPT),
                "-ProjectRoot",
                str(self.project),
                "-ProjectId",
                "take-me",
                "-ProjectPrefix",
                "TAKE",
                "-Title",
                "달을 향한 약속",
                "-TemplateRoot",
                str(TEMPLATES),
                *extra,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_scaffolds_authority_files_and_project_directories(self) -> None:
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8-sig"))
        self.assertEqual("take-me", project["project_id"])
        self.assertEqual("TAKE", project["project_prefix"])
        self.assertEqual("달을 향한 약속", project["title"])
        self.assertEqual("Initialized Cinema Studio project.", project["notes"])
        for authority in (
            self.project / "01_story" / "STORY_CONTRACT.md",
            self.project / "03_lookdev" / "VISUAL_BIBLE.md",
        ):
            content = authority.read_text(encoding="utf-8-sig")
            self.assertIn("Project ID: `take-me`", content)
            self.assertNotIn("Project ID: `new-project`", content)
        expected = [
            "01_story/STORY_CONTRACT.md",
            "01_story/history/story-contract",
            "00_schemas/project.schema.json",
            "00_schemas/schema-manifest.json",
            "02_storyboard/storyboard.json",
            "02_storyboard/history",
            "03_lookdev/VISUAL_BIBLE.md",
            "03_lookdev/history/visual-bible",
            "04_assets/records",
            "04_assets/asset-index.json",
            "05_shots",
            "06_source_library/source_manifest.json",
            "06_source_library/history",
            "07_edit/timeline.json",
            "07_edit/records",
            "08_delivery/delivery.json",
            "09_approvals/_templates",
            "99_logs",
        ]
        for relative in expected:
            self.assertTrue((self.project / relative).exists(), relative)
        for obsolete in ("01_story/approvals", "02_storyboard/approvals", "03_lookdev/approvals"):
            self.assertFalse((self.project / obsolete).exists(), obsolete)
        for relative in (
            "04_assets/_templates/CHARACTER_PROFILE.yaml",
            "04_assets/_templates/LOCATION_MAP.yaml",
        ):
            content = (self.project / relative).read_text(encoding="utf-8-sig")
            self.assertEqual("take-me", yaml.safe_load(content)["project_id"])
            self.assertNotIn("new-project", content)
        for relative in (
            "project.json",
            "02_storyboard/storyboard.json",
            "04_assets/_templates/ASSET_RECORD.json",
            "05_shots/_templates/SHOT_CARD.json",
            "05_shots/_templates/TAKE_RECORD.json",
            "06_source_library/source_manifest.json",
            "07_edit/timeline.json",
            "08_delivery/delivery.json",
            "09_approvals/_templates/APPROVAL.json",
        ):
            instance_path = self.project / relative
            instance = json.loads(instance_path.read_text(encoding="utf-8-sig"))
            schema_names = {
                "cinema-studio-pipeline/project@2.0.0": "project.schema.json",
                "cinema-studio-pipeline/storyboard@2.0.0": "storyboard.schema.json",
                "cinema-studio-pipeline/asset@2.0.0": "asset.schema.json",
                "cinema-studio-pipeline/shot@2.0.0": "shot.schema.json",
                "cinema-studio-pipeline/take@2.0.0": "take.schema.json",
                "cinema-studio-pipeline/source-library@2.0.0": "source-library.schema.json",
                "cinema-studio-pipeline/timeline@2.0.0": "timeline.schema.json",
                "cinema-studio-pipeline/delivery@2.0.0": "delivery.schema.json",
                "cinema-studio-pipeline/approval@2.0.0": "approval.schema.json",
            }
            if "$schema" in instance:
                schema_path = (instance_path.parent / instance["$schema"]).resolve()
            else:
                schema_path = self.project / "00_schemas" / schema_names[instance["schema_id"]]
            self.assertTrue(schema_path.is_file(), f"broken $schema in {relative}: {schema_path}")
            try:
                import jsonschema
            except ImportError:
                continue
            schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
            validator_class = jsonschema.validators.validator_for(schema)
            validator_class.check_schema(schema)
            errors = list(validator_class(schema).iter_errors(instance))
            self.assertEqual([], errors, f"schema-invalid initialized file {relative}: {errors}")

    def test_default_cli_resolves_templates_from_the_script_directory(self) -> None:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-File",
                str(SCRIPT),
                "-ProjectRoot",
                str(self.project),
                "-ProjectId",
                "moon-promise-forward",
                "-ProjectPrefix",
                "MPF",
                "-Title",
                "Moon Promise Forward Test",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        project = json.loads((self.project / "project.json").read_text(encoding="utf-8-sig"))
        self.assertEqual("moon-promise-forward", project["project_id"])
        self.assertEqual("MPF", project["project_prefix"])
        self.assertEqual("Moon Promise Forward Test", project["title"])

    def test_raw_yaml_templates_are_parseable_with_literal_project_placeholder(self) -> None:
        for name in ("CHARACTER_PROFILE.yaml", "LOCATION_MAP.yaml"):
            with self.subTest(name=name):
                payload = yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))
                self.assertEqual("{{PROJECT_ID}}", payload["project_id"])

    def test_refuses_existing_managed_files_without_force_and_preserves_unknown_files(self) -> None:
        self.assertEqual(0, self._run().returncode)
        custom = self.project / "my_notes.txt"
        custom.write_text("preserve", encoding="utf-8")
        second = self._run()
        self.assertNotEqual(0, second.returncode)
        self.assertEqual("preserve", custom.read_text(encoding="utf-8"))

    def test_force_refuses_a_directory_at_a_managed_file_target(self) -> None:
        self.project.mkdir(parents=True)
        conflicting = self.project / "project.json"
        conflicting.mkdir()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertTrue(conflicting.is_dir())
        self.assertEqual([], list(conflicting.iterdir()))

    def test_force_preflight_preserves_all_managed_bytes_when_a_late_target_is_a_directory(self) -> None:
        initialized = self._run()
        self.assertEqual(0, initialized.returncode, initialized.stderr + initialized.stdout)
        story = self.project / "01_story" / "STORY_CONTRACT.md"
        story.write_text("USER MARKER", encoding="utf-8")
        conflicting = self.project / "04_assets" / "asset-index.json"
        conflicting.unlink()
        conflicting.mkdir()
        project_before = (self.project / "project.json").read_bytes()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertEqual("USER MARKER", story.read_text(encoding="utf-8"))
        self.assertEqual(project_before, (self.project / "project.json").read_bytes())
        self.assertTrue(conflicting.is_dir())

    def test_force_rejects_oversized_project_and_approval_json_before_any_write(self) -> None:
        self.project.mkdir(parents=True)
        oversized_project = self.project / "project.json"
        with oversized_project.open("wb") as handle:
            handle.write(b"{}")
            handle.truncate(MAX_INIT_INPUT_BYTES + 1)

        project_result = self._run("-Force")

        self.assertNotEqual(0, project_result.returncode)
        self.assertIn("safe size limit", project_result.stderr + project_result.stdout)
        self.assertEqual(MAX_INIT_INPUT_BYTES + 1, oversized_project.stat().st_size)
        self.assertFalse((self.project / "01_story" / "STORY_CONTRACT.md").exists())

        shutil.rmtree(self.project)
        initialized = self._run()
        self.assertEqual(0, initialized.returncode, initialized.stderr + initialized.stdout)
        story = self.project / "01_story" / "STORY_CONTRACT.md"
        story.write_text("USER MARKER", encoding="utf-8")
        approval = self.project / "09_approvals" / "oversized.json"
        with approval.open("wb") as handle:
            handle.write(b"{}")
            handle.truncate(MAX_INIT_INPUT_BYTES + 1)

        approval_result = self._run("-Force")

        self.assertNotEqual(0, approval_result.returncode)
        self.assertIn("safe size limit", approval_result.stderr + approval_result.stdout)
        self.assertEqual("USER MARKER", story.read_text(encoding="utf-8"))

    def test_force_accepts_an_exactly_maximum_sized_valid_project_json(self) -> None:
        initialized = self._run()
        self.assertEqual(0, initialized.returncode, initialized.stderr + initialized.stdout)
        project_path = self.project / "project.json"
        compact = json.dumps(
            json.loads(project_path.read_text(encoding="utf-8-sig")),
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertLess(len(compact), MAX_INIT_INPUT_BYTES)
        project_path.write_bytes(compact + b" " * (MAX_INIT_INPUT_BYTES - len(compact)))

        result = self._run("-Force")

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertEqual("take-me", json.loads(project_path.read_text(encoding="utf-8-sig"))["project_id"])

    def test_oversized_trusted_template_fails_before_project_creation(self) -> None:
        bundle = Path(self.temp_dir.name) / "bundle"
        template_copy = bundle / "templates"
        shutil.copytree(TEMPLATES, template_copy)
        shutil.copytree(SKILL_ROOT / "schemas", bundle / "schemas")
        oversized = template_copy / "REVIEW_REPORT.md"
        with oversized.open("wb") as handle:
            handle.write(b"report")
            handle.truncate(MAX_INIT_INPUT_BYTES + 1)

        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-File", str(SCRIPT),
                "-ProjectRoot", str(self.project), "-ProjectId", "take-me",
                "-ProjectPrefix", "TAKE", "-Title", "Bounded template",
                "-TemplateRoot", str(template_copy),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("safe size limit", result.stderr + result.stdout)
        self.assertFalse(self.project.exists())

    def test_bounded_reader_rejects_growth_after_its_initial_length_check(self) -> None:
        escaped_script = str(SCRIPT).replace("'", "''")
        command = f"""
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{escaped_script}', [ref]$tokens, [ref]$parseErrors)
$functionAst = $ast.Find({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-BoundedUtf8Text' }}, $true)
Invoke-Expression $functionAst.Extent.Text
$MaxInitInputBytes = 8
$stream = [System.IO.MemoryStream]::new()
0..7 | ForEach-Object {{ $stream.WriteByte(0x20) }}
$stream.Position = 0
$grow = {{
    $stream.Position = $stream.Length
    $stream.WriteByte(0x20)
    $stream.Position = 0
}}
try {{
    Read-BoundedUtf8Text -Path 'memory-test' -InputStream $stream -AfterLengthCheck $grow | Out-Null
    Write-Output 'UNEXPECTED_SUCCESS'
    exit 0
}}
catch {{
    Write-Output $_.Exception.Message
    exit 7
}}
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(7, result.returncode, result.stderr + result.stdout)
        self.assertIn("safe size limit", result.stdout)

    def test_whatif_does_not_create_the_project(self) -> None:
        result = self._run("-WhatIf")
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertFalse(self.project.exists())

    def test_rejects_skill_descendants_as_project_roots(self) -> None:
        unsafe = SKILL_ROOT / "unsafe-project-test"
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                "-ProjectRoot", str(unsafe), "-ProjectId", "unsafe", "-ProjectPrefix", "SAFE",
                "-Title", "Unsafe", "-TemplateRoot", str(TEMPLATES), "-WhatIf",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(unsafe.exists())

    def test_initialized_project_passes_full_snapshot_validation(self) -> None:
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from validate_project import validate_project

            validation = validate_project(self.project)
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass
        self.assertTrue(validation["ok"], validation)
        self.assertEqual("project_snapshot", validation["schema_source"])

    def test_fresh_project_story_review_and_approval_advances_to_storyboard(self) -> None:
        result = self._run()
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from prepare_review import prepare_review
            from record_decision import record_decision

            project_path = self.project / "project.json"
            story_path = self.project / "01_story" / "STORY_CONTRACT.md"

            with patch(
                "decision_receipts.receipt_store_root",
                return_value=self.receipt_store,
            ):
                prepared = prepare_review(
                    self.project,
                    "STORY",
                    "story-contract",
                    requested_by="director",
                    expected_project_sha256=hashlib.sha256(project_path.read_bytes()).hexdigest(),
                    expected_subject_sha256=hashlib.sha256(story_path.read_bytes()).hexdigest(),
                    apply=True,
                )
                self.assertTrue(prepared["review_prepared"], prepared)
                self.assertTrue(prepared["gate_activated"], prepared)
                approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"

                decided = record_decision(
                    self.project,
                    "APR_STORY_0001",
                    "approve",
                    actor="project-owner",
                    reference="chat-fresh-init",
                    notes="approved",
                    expected_project_sha256=hashlib.sha256(project_path.read_bytes()).hexdigest(),
                    expected_approval_sha256=hashlib.sha256(approval_path.read_bytes()).hexdigest(),
                    expected_subject_sha256=hashlib.sha256(story_path.read_bytes()).hexdigest(),
                    apply=True,
                )
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass

        self.assertTrue(decided["decision_recorded"], decided)
        self.assertTrue(decided["gate_activated"], decided)
        self.assertTrue((self.receipt_store / "hmac.key").is_file())
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        self.assertEqual("USER_APPROVED", project["stage_gates"]["STORY"])
        self.assertEqual("STORYBOARD", project["current_stage"])
        self.assertIn("APR_STORY_0001", project["active_approval_ids"])

    def test_validation_fails_closed_for_missing_snapshot_schema_or_engine(self) -> None:
        self.assertEqual(0, self._run().returncode)
        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from validate_project import validate_project

            approval_schema = self.project / "00_schemas" / "approval.schema.json"
            approval_schema.unlink()
            missing_schema = validate_project(self.project)
            self.assertIn("SCHEMA_MISSING", {item["code"] for item in missing_schema["errors"]})

            shutil.copy2(SKILL_ROOT / "schemas" / "approval.schema.json", approval_schema)
            with patch.dict(sys.modules, {"jsonschema": None}):
                missing_engine = validate_project(self.project)
            self.assertIn("SCHEMA_ENGINE_MISSING", {item["code"] for item in missing_engine["errors"]})
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass

    def test_validation_requires_stable_schema_id(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project.pop("schema_id")
        project_path.write_text(json.dumps(project), encoding="utf-8")
        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from validate_project import validate_project

            validation = validate_project(self.project)
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass
        self.assertIn("SCHEMA_ID_MISSING", {item["code"] for item in validation["errors"]})

    def test_schema_validation_enforces_date_time_formats(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["created_at"] = "definitely-not-a-date-time"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        approval = json.loads(
            (self.project / "09_approvals" / "_templates" / "APPROVAL.json").read_text(encoding="utf-8-sig")
        )
        approval["$schema"] = "../00_schemas/approval.schema.json"
        approval["project_id"] = "take-me"
        approval["decided_at"] = "also-not-a-date-time"
        (self.project / "09_approvals" / "APR_STORY_0001.json").write_text(
            json.dumps(approval), encoding="utf-8"
        )
        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from validate_project import validate_project

            validation = validate_project(self.project)
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass
        schema_errors = [item for item in validation["errors"] if item["code"] == "SCHEMA_ERROR"]
        self.assertTrue(any("created_at" in item["message"] for item in schema_errors), validation)
        self.assertTrue(any("decided_at" in item["message"] for item in schema_errors), validation)

    def test_project_snapshot_must_match_the_trusted_installed_schema_manifest(self) -> None:
        self.assertEqual(0, self._run().returncode)
        schema_path = self.project / "00_schemas" / "shot.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
        schema["description"] = "tampered project-controlled schema"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")

        scripts = SKILL_ROOT / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            from validate_project import validate_project

            validation = validate_project(self.project)
        finally:
            try:
                sys.path.remove(str(scripts))
            except ValueError:
                pass
        self.assertIn("SCHEMA_SNAPSHOT_HASH_MISMATCH", {item["code"] for item in validation["errors"]})

    def test_rejects_project_roots_beneath_a_junction(self) -> None:
        base = Path(self.temp_dir.name)
        actual = base / "junction-target"
        junction = base / "junction-link"
        actual.mkdir()
        created = subprocess.run(
            [
                "cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(actual),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if created.returncode != 0:
            self.skipTest(f"junction creation unavailable: {created.stderr}")
        original_project = self.project
        self.project = junction / "nested-project"
        try:
            result = self._run()
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertFalse((actual / "nested-project").exists())
        finally:
            self.project = original_project
            try:
                junction.rmdir()
            except OSError:
                pass

    def test_force_cannot_reinitialize_an_approved_project(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["stage_gates"]["STORY"] = "USER_APPROVED"
        project["active_approval_ids"] = ["APR_STORY_0001"]
        project_path.write_text(json.dumps(project), encoding="utf-8")
        before = project_path.read_bytes()

        result = self._run("-Force")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, project_path.read_bytes())

    def test_force_rejects_surviving_central_user_approval_even_when_project_gates_are_stale(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"
        approval_path.write_text(
            json.dumps(
                {
                    "project_id": "take-me",
                    "approval_id": "APR_STORY_0001",
                    "gate": "STORY",
                    "review_status": "USER_APPROVED",
                    "superseded_by_approval_id": None,
                }
            ),
            encoding="utf-8",
        )

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("approval", (result.stderr + result.stdout).casefold())
        self.assertEqual(before, project_path.read_bytes())

    def test_force_rejects_pending_and_rejected_central_review_history(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"
        for status in ("USER_REVIEW_REQUIRED", "REJECTED"):
            with self.subTest(status=status):
                approval_path.write_text(
                    json.dumps(
                        {
                            "project_id": "take-me",
                            "approval_id": "APR_STORY_0001",
                            "gate": "STORY",
                            "review_status": status,
                        }
                    ),
                    encoding="utf-8",
                )
                result = self._run("-Force")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, project_path.read_bytes())

    def test_force_rejects_pending_review_in_project_configured_approvals_path(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["paths"]["approvals"] = "custom/review-authority"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        before = project_path.read_bytes()
        approval_path = self.project / "custom" / "review-authority" / "APR_STORY_0001.json"
        approval_path.parent.mkdir(parents=True)
        for status in ("USER_REVIEW_REQUIRED", "REJECTED"):
            with self.subTest(status=status):
                approval_path.write_text(
                    json.dumps(
                        {
                            "project_id": "take-me",
                            "approval_id": "APR_STORY_0001",
                            "gate": "STORY",
                            "review_status": status,
                        }
                    ),
                    encoding="utf-8",
                )

                result = self._run("-Force")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("approval", (result.stderr + result.stdout).casefold())
                self.assertEqual(before, project_path.read_bytes())

    def test_force_fails_closed_when_configured_approval_pointer_is_missing(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        custom_root = self.project / "custom" / "review-authority"
        project["paths"]["approvals"] = "custom/review-authority"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        custom_approval = custom_root / "APR_STORY_0001.json"
        custom_approval.parent.mkdir(parents=True)
        custom_approval.write_text(
            json.dumps(
                {
                    "project_id": "take-me",
                    "approval_id": "APR_STORY_0001",
                    "gate": "STORY",
                    "review_status": "USER_REVIEW_REQUIRED",
                }
            ),
            encoding="utf-8",
        )
        del project["paths"]["approvals"]
        project_path.write_text(json.dumps(project), encoding="utf-8")
        before_project = project_path.read_bytes()
        before_approval = custom_approval.read_bytes()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("approval", (result.stderr + result.stdout).casefold())
        self.assertEqual(before_project, project_path.read_bytes())
        self.assertEqual(before_approval, custom_approval.read_bytes())

    def test_force_fails_closed_when_required_authority_pointer_is_missing(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        del project["authority_files"]["source_manifest"]
        project_path.write_text(json.dumps(project), encoding="utf-8")
        before = project_path.read_bytes()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("authority", (result.stderr + result.stdout).casefold())
        self.assertEqual(before, project_path.read_bytes())

    def test_force_rejects_locked_project_configured_authority(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["authority_files"]["source_manifest"] = "custom/source/manifest.json"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        before = project_path.read_bytes()
        custom = self.project / "custom" / "source" / "manifest.json"
        custom.parent.mkdir(parents=True)
        custom.write_text(
            json.dumps({"lock_status": "SOURCE_LOCKED"}), encoding="utf-8"
        )

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("locked", (result.stderr + result.stdout).casefold())
        self.assertEqual(before, project_path.read_bytes())

    def test_force_fails_closed_on_unsafe_project_configured_paths(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        for section, key in (
            ("paths", "approvals"),
            ("paths", "shots"),
            ("authority_files", "timeline"),
        ):
            with self.subTest(section=section, key=key):
                project = json.loads(before.decode("utf-8-sig"))
                project[section][key] = "../outside/authority.json"
                project_path.write_text(json.dumps(project), encoding="utf-8")

                result = self._run("-Force")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("unsafe", (result.stderr + result.stdout).casefold())
                self.assertEqual(
                    "../outside/authority.json",
                    json.loads(project_path.read_text(encoding="utf-8"))[section][key],
                )
                project_path.write_bytes(before)

    def test_force_scans_protected_records_under_a_custom_shots_root(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["paths"]["shots"] = "custom/production-shots"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        protected = (
            self.project
            / "custom"
            / "production-shots"
            / "S01_SH001"
            / "shot.json"
        )
        protected.parent.mkdir(parents=True)
        protected.write_text(
            json.dumps(
                {
                    "project_id": "take-me",
                    "shot_id": "S01_SH001",
                    "review_status": "USER_APPROVED",
                }
            ),
            encoding="utf-8",
        )
        before_project = project_path.read_bytes()
        before_record = protected.read_bytes()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("protected", (result.stderr + result.stdout).casefold())
        self.assertEqual(before_project, project_path.read_bytes())
        self.assertEqual(before_record, protected.read_bytes())

    def test_force_fails_closed_on_malformed_configured_approval_path(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        for malformed in (None, 7, ""):
            with self.subTest(value=malformed):
                project = json.loads(before.decode("utf-8-sig"))
                project["paths"]["approvals"] = malformed
                project_path.write_text(json.dumps(project), encoding="utf-8")

                result = self._run("-Force")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("approval", (result.stderr + result.stdout).casefold())
                self.assertEqual(
                    malformed,
                    json.loads(project_path.read_text(encoding="utf-8"))["paths"]["approvals"],
                )
                project_path.write_bytes(before)

    def test_force_fails_closed_on_malformed_authority_map(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        for malformed in (None, 7, ""):
            with self.subTest(value=malformed):
                project = json.loads(before.decode("utf-8-sig"))
                project["authority_files"] = malformed
                project_path.write_text(json.dumps(project), encoding="utf-8")

                result = self._run("-Force")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("authority", (result.stderr + result.stdout).casefold())
                self.assertEqual(
                    malformed,
                    json.loads(project_path.read_text(encoding="utf-8"))["authority_files"],
                )
                project_path.write_bytes(before)

    def test_force_fails_closed_on_malformed_project_paths_map(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        before = project_path.read_bytes()
        for malformed in (None, 7, ""):
            with self.subTest(value=malformed):
                project = json.loads(before.decode("utf-8-sig"))
                project["paths"] = malformed
                project_path.write_text(json.dumps(project), encoding="utf-8")

                result = self._run("-Force")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("path", (result.stderr + result.stdout).casefold())
                self.assertEqual(
                    malformed,
                    json.loads(project_path.read_text(encoding="utf-8"))["paths"],
                )
                project_path.write_bytes(before)

    def test_force_guard_detects_legacy_approval_and_approved_managed_artifact(self) -> None:
        self.assertEqual(0, self._run().returncode)
        legacy = self.project / "01_story" / "approvals" / "legacy.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(json.dumps({"review_status": "USER_APPROVED"}), encoding="utf-8")
        result = self._run("-Force")
        self.assertNotEqual(0, result.returncode)

        legacy.unlink()
        delivery_path = self.project / "08_delivery" / "delivery.json"
        delivery = json.loads(delivery_path.read_text(encoding="utf-8-sig"))
        delivery["review_status"] = "USER_APPROVED"
        delivery["approval_id"] = "APR_FINISH_0001"
        delivery_path.write_text(json.dumps(delivery), encoding="utf-8")
        result = self._run("-Force")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("protected review state", (result.stderr + result.stdout).casefold())

    def test_force_guard_detects_an_approved_versioned_timeline(self) -> None:
        self.assertEqual(0, self._run().returncode)
        seed = json.loads((self.project / "07_edit" / "timeline.json").read_text(encoding="utf-8-sig"))
        seed.update(
            {
                "version": 2,
                "review_status": "USER_APPROVED",
                "lock_status": "PICTURE_LOCKED",
                "approval_id": "APR_EDIT_0002",
            }
        )
        versioned = self.project / "07_edit" / "records" / "main_timeline" / "v002" / "timeline.json"
        versioned.parent.mkdir(parents=True, exist_ok=True)
        versioned.write_text(json.dumps(seed), encoding="utf-8")

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("protected review state", (result.stderr + result.stdout).casefold())

    def test_force_fails_closed_on_scalar_configured_authority_json(self) -> None:
        self.assertEqual(0, self._run().returncode)
        source_manifest = self.project / "06_source_library" / "source_manifest.json"
        source_manifest.write_text("7", encoding="utf-8")
        before = source_manifest.read_bytes()

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("object", (result.stderr + result.stdout).casefold())
        self.assertEqual(before, source_manifest.read_bytes())

    def test_force_fails_closed_on_scalar_managed_json_in_custom_root(self) -> None:
        self.assertEqual(0, self._run().returncode)
        project_path = self.project / "project.json"
        project = json.loads(project_path.read_text(encoding="utf-8-sig"))
        project["paths"]["shots"] = "custom/production-shots"
        project_path.write_text(json.dumps(project), encoding="utf-8")
        managed = self.project / "custom" / "production-shots" / "S01_SH001" / "shot.json"
        managed.parent.mkdir(parents=True)
        managed.write_text("[]", encoding="utf-8")

        result = self._run("-Force")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("object", (result.stderr + result.stdout).casefold())
        self.assertEqual(b"[]", managed.read_bytes())

    def test_allows_onedrive_cloud_reparse_without_name_redirection(self) -> None:
        onedrive = Path.home() / "OneDrive"
        if not onedrive.is_dir():
            self.skipTest("OneDrive is not available on this host")
        original_project = self.project
        with tempfile.TemporaryDirectory(dir=onedrive, prefix="cinema-init-test-") as cloud_temp:
            self.project = Path(cloud_temp) / "project"
            try:
                result = self._run()
                self.assertEqual(0, result.returncode, result.stderr + result.stdout)
                self.assertTrue((self.project / "project.json").is_file())
            finally:
                self.project = original_project


if __name__ == "__main__":
    unittest.main()
