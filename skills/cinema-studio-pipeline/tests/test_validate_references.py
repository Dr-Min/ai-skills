import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ValidateReferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        write_json(self.project / "project.json", {"project_id": "take-me", "authority_files": {"asset_records_root": "04_assets/records"}, "paths": {"shots": "05_shots", "approvals": "09_approvals"}})
        assets = [
            {
                "asset_id": "woman_neutral",
                "kind": "CHARACTER",
                "state": {"isolation": "REQUIRED", "label": "neutral", "mutually_exclusive_with": ["woman_wounded"]},
            },
            {
                "asset_id": "woman_wounded",
                "kind": "CHARACTER",
                "state": {"isolation": "REQUIRED", "label": "wounded", "mutually_exclusive_with": ["woman_neutral"]},
            },
            {
                "asset_id": "moon_rooftop",
                "kind": "LOCATION",
                "state": {"isolation": "NOT_APPLICABLE", "label": "night", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "take_me_audio",
                "kind": "AUDIO",
                "state": {"isolation": "NOT_APPLICABLE", "label": "master", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "woman_voice_v1",
                "kind": "VOICE",
                "state": {"isolation": "NOT_APPLICABLE", "label": "base", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "man_voice_v1",
                "kind": "VOICE",
                "state": {"isolation": "NOT_APPLICABLE", "label": "base", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "man_neutral",
                "kind": "CHARACTER",
                "state": {"isolation": "NOT_APPLICABLE", "label": "neutral", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "woman_wardrobe_base",
                "kind": "WARDROBE",
                "state": {"isolation": "NOT_APPLICABLE", "label": "base", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "man_wardrobe_base",
                "kind": "WARDROBE",
                "state": {"isolation": "NOT_APPLICABLE", "label": "base", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "woman_state_clean",
                "kind": "CHARACTER",
                "state": {"isolation": "NOT_APPLICABLE", "label": "clean", "mutually_exclusive_with": []},
            },
            {
                "asset_id": "man_state_clean",
                "kind": "CHARACTER",
                "state": {"isolation": "NOT_APPLICABLE", "label": "clean", "mutually_exclusive_with": []},
            },
        ]
        for index, asset in enumerate(assets, start=1):
            master = self.project / "04_assets" / "masters" / f"{asset['asset_id']}.bin"
            master.parent.mkdir(parents=True, exist_ok=True)
            master.write_bytes(asset["asset_id"].encode())
            digest = hashlib.sha256(master.read_bytes()).hexdigest()
            asset["project_id"] = "take-me"
            asset["files"] = {"immutable_master": {"path": master.relative_to(self.project).as_posix(), "sha256": digest}}
            lineage = {"output_sha256": digest}
            if asset["asset_id"] == "woman_wounded":
                lineage["immutable_master_asset_id"] = "woman_neutral"
            if asset["asset_id"] == "woman_voice_v1":
                lineage["parent_asset_id"] = "woman_neutral"
            if asset["asset_id"] == "man_voice_v1":
                lineage["parent_asset_id"] = "man_neutral"
            asset["lineage"] = lineage
            write_json(self.project / "04_assets" / "records" / asset["asset_id"] / "asset.json", asset)
            write_json(
                self.project / "09_approvals" / f"APR_ASSET_LOCK_{index:04d}.json",
                {
                    "project_id": "take-me",
                    "approval_id": f"APR_ASSET_LOCK_{index:04d}",
                    "gate": "ASSET_LOCK",
                    "subject_type": "ASSET",
                    "subject_id": asset["asset_id"],
                    "subject_sha256": digest,
                    "review_status": "USER_APPROVED",
                    "superseded_by_approval_id": None,
                    "evidence": [{"path": master.relative_to(self.project).as_posix(), "sha256": digest, "verified_claim": "asset master"}],
                },
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _shot(self, active_assets: list[dict], **overrides: object) -> Path:
        payload = {
            "shot_id": "S01_SH010",
            "format_mode": "REFERENCE_TEXT_NATIVE",
            "active_assets": active_assets,
            "boundary_frames": {},
        }
        payload.update(overrides)
        shot_path = self.project / "05_shots" / "S01_SH010" / "shot.json"
        write_json(shot_path, payload)
        return shot_path

    def test_accepts_compatible_roles_and_one_state_per_logical_asset(self) -> None:
        shot_path = self._shot(
            [
                {
                    "asset_id": "woman_neutral",
                    "role": "IDENTITY",
                    "state_label": "neutral",
                },
                {"asset_id": "moon_rooftop", "role": "LOCATION_GEOMETRY"},
            ]
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertTrue(result["ok"], result)

    def test_rejects_mutually_exclusive_states_and_kind_role_mismatch(self) -> None:
        shot_path = self._shot(
            [
                {
                    "asset_id": "woman_neutral",
                    "role": "IDENTITY",
                    "state_label": "neutral",
                },
                {
                    "asset_id": "woman_wounded",
                    "role": "STATE",
                    "state_label": "wounded",
                },
                {"asset_id": "take_me_audio", "role": "LOCATION_GEOMETRY"},
            ]
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_MUTEX_REFERENCE", codes)
        self.assertIn("E_REFERENCE_ROLE_CONFLICT", codes)

    def test_enforces_required_inputs_for_special_generation_modes(self) -> None:
        shot_path = self._shot(
            [{"asset_id": "woman_neutral", "role": "IDENTITY"}],
            format_mode="MUSIC_LIPSYNC",
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertIn(
            "E_REFERENCE_ROLE_CONFLICT", {item["code"] for item in result["errors"]}
        )

    def test_dialogue_requires_an_approved_voice_asset_not_only_generic_audio(self) -> None:
        from validate_references import validate_references

        shot_path = self._shot(
            [{"asset_id": "take_me_audio", "role": "AUDIO"}],
            audio={
                "dialogue": [
                    {
                        "speaker_asset_id": "woman_neutral",
                        "voice_asset_id": "take_me_audio",
                        "line": "Take me there.",
                    }
                ]
            },
        )
        missing_voice = validate_references(self.project, shot_paths=[shot_path])
        self.assertIn(
            "E_REFERENCE_ROLE_CONFLICT",
            {item["code"] for item in missing_voice["errors"]},
        )
        self.assertTrue(
            any("VOICE" in item["message"] for item in missing_voice["errors"]),
            missing_voice,
        )

        shot_path = self._shot(
            [
                {"asset_id": "woman_neutral", "role": "IDENTITY"},
                {"asset_id": "woman_voice_v1", "role": "AUDIO"},
            ],
            audio={
                "dialogue": [
                    {
                        "speaker_asset_id": "woman_neutral",
                        "voice_asset_id": "woman_voice_v1",
                        "line": "Take me there.",
                    }
                ]
            },
        )
        with_voice = validate_references(self.project, shot_paths=[shot_path])
        self.assertTrue(with_voice["ok"], with_voice)

    def test_two_speaker_dialogue_accepts_two_explicit_voice_assets(self) -> None:
        shot_path = self._shot(
            [
                {"asset_id": "woman_neutral", "role": "IDENTITY"},
                {"asset_id": "man_neutral", "role": "IDENTITY"},
                {"asset_id": "woman_voice_v1", "role": "AUDIO"},
                {"asset_id": "man_voice_v1", "role": "AUDIO"},
            ],
            audio={
                "dialogue": [
                    {
                        "speaker_asset_id": "woman_neutral",
                        "voice_asset_id": "woman_voice_v1",
                        "line": "Do you remember?",
                    },
                    {
                        "speaker_asset_id": "man_neutral",
                        "voice_asset_id": "man_voice_v1",
                        "line": "I remember.",
                    },
                ]
            },
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertTrue(result["ok"], result)

    def test_dialogue_rejects_voice_owned_by_another_character(self) -> None:
        shot_path = self._shot(
            [
                {"asset_id": "woman_wounded", "role": "STATE", "state_label": "wounded"},
                {"asset_id": "man_voice_v1", "role": "AUDIO"},
            ],
            audio={
                "dialogue": [
                    {
                        "speaker_asset_id": "woman_wounded",
                        "voice_asset_id": "man_voice_v1",
                        "line": "This is not my voice.",
                    }
                ]
            },
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertFalse(result["ok"], result)
        self.assertTrue(
            any("same character" in item["message"] for item in result["errors"]),
            result,
        )

    def test_ensemble_accepts_identity_wardrobe_and_state_per_character(self) -> None:
        shot_path = self._shot(
            [
                {"asset_id": "woman_neutral", "role": "IDENTITY", "state_label": "neutral"},
                {"asset_id": "man_neutral", "role": "IDENTITY", "state_label": "neutral"},
                {"asset_id": "woman_wardrobe_base", "role": "WARDROBE", "state_label": "base"},
                {"asset_id": "man_wardrobe_base", "role": "WARDROBE", "state_label": "base"},
                {"asset_id": "woman_state_clean", "role": "STATE", "state_label": "clean"},
                {"asset_id": "man_state_clean", "role": "STATE", "state_label": "clean"},
            ]
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertTrue(result["ok"], result)

    def test_dialogue_rejects_a_missing_per_line_voice_binding(self) -> None:
        shot_path = self._shot(
            [{"asset_id": "woman_voice_v1", "role": "AUDIO"}],
            audio={
                "dialogue": [
                    {
                        "speaker_asset_id": "woman_neutral",
                        "voice_asset_id": None,
                        "line": "Take me there.",
                    }
                ]
            },
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        self.assertTrue(
            any("Dialogue line 0" in item["message"] for item in result["errors"]),
            result,
        )

    def test_rejects_duplicate_scene_singleton_roles_and_unknown_assets(self) -> None:
        shot_path = self._shot(
            [
                {"asset_id": "moon_rooftop", "role": "LOCATION_GEOMETRY"},
                {"asset_id": "moon_rooftop", "role": "LOCATION_GEOMETRY"},
                {"asset_id": "not_registered", "role": "PROP_FUNCTION"},
            ]
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_REFERENCE_ROLE_CONFLICT", codes)
        self.assertIn("E_UNAPPROVED_INPUT", codes)

    def test_boundary_assets_must_exist_and_be_user_approved(self) -> None:
        unapproved_path = self.project / "09_approvals" / "APR_ASSET_LOCK_0003.json"
        unapproved = json.loads(unapproved_path.read_text(encoding="utf-8"))
        unapproved["review_status"] = "INTERNAL_REVIEW"
        write_json(unapproved_path, unapproved)
        shot_path = self._shot(
            [],
            format_mode="BOUNDARY_FRAME",
            boundary_frames={"start_asset_id": "moon_rooftop", "end_asset_id": "unknown_frame"},
        )

        from validate_references import validate_references

        result = validate_references(self.project, shot_paths=[shot_path])
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("E_UNAPPROVED_INPUT", codes)

    def test_rejects_explicit_shot_path_outside_project(self) -> None:
        outside = self.project.parent / f"{self.project.name}-outside-shot.json"
        write_json(outside, {"shot_id": "S01_SH999", "active_assets": []})
        try:
            from validate_references import validate_references

            result = validate_references(self.project, shot_paths=[outside])
        finally:
            outside.unlink(missing_ok=True)
        self.assertIn("PATH_ESCAPE", {item["code"] for item in result["errors"]})


if __name__ == "__main__":
    unittest.main()
