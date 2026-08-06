from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beatcut_core import parse_hint, select_window, validate_capcut_stage, validate_plan


def candidate(time_value: float, strength: float = 10.0) -> dict[str, float]:
    return {"time": time_value, "strength": strength, "confidence": min(1.0, strength / 10.0)}


class HintTests(unittest.TestCase):
    def test_closed_and_open_hints(self) -> None:
        self.assertEqual(parse_hint("4:6"), {"start": 4.0, "end": 6.0})
        self.assertEqual(parse_hint("9:"), {"start": 9.0, "end": None})
        self.assertEqual(parse_hint("4-6"), {"start": 4.0, "end": 6.0})

    def test_invalid_hint(self) -> None:
        with self.assertRaises(ValueError):
            parse_hint("6:4")


class WindowTests(unittest.TestCase):
    def test_closed_hint_releases_on_an_actual_attack(self) -> None:
        candidates = [candidate(value) for value in (3.70, 4.08, 4.25, 4.42, 5.75, 6.09, 6.41)]
        window = select_window(candidates, [4.08, 4.58, 5.08, 5.58, 6.08], {"start": 4.0, "end": 6.0}, 8.0)
        self.assertEqual(window["start_detected"], 4.08)
        self.assertEqual(window["release_detected"], 6.09)
        self.assertTrue(all(item["time"] < 6.09 for item in window["cuts"]))

    def test_open_hint_uses_first_attack_after_dense_run_gap(self) -> None:
        dense = [9.09, 9.28, 9.50, 9.68, 9.86, 10.04, 10.22, 10.40, 10.58, 10.76, 10.94, 11.12]
        candidates = [candidate(value) for value in [*dense, 11.49, 11.67]]
        window = select_window(candidates, [9.1, 9.6, 10.1, 10.6, 11.1, 11.6], {"start": 9.0, "end": None}, 13.0)
        self.assertEqual(window["start_detected"], 9.09)
        self.assertEqual(window["release_detected"], 11.49)
        self.assertEqual(window["release_reason"], "first_actual_attack_after_dense_run_gap")


class ValidationTests(unittest.TestCase):
    def test_plan_validation(self) -> None:
        plan = {
            "schema_version": 1,
            "audio": {},
            "settings": {},
            "analysis": {},
            "windows": [],
            "timeline": {"total_frames": 300, "cut_frames": [30, 60, 90]},
            "status": "diagnostic_review_required",
        }
        self.assertEqual(validate_plan(plan), [])
        plan["timeline"]["cut_frames"] = [60, 30]
        self.assertIn("cut_frames must be unique and sorted", validate_plan(plan))

    def test_capcut_stage_references_and_contiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_text:
            root = Path(temp_text)
            video_a = root / "a.mp4"
            video_b = root / "b.mp4"
            audio = root / "music.wav"
            for path in (video_a, video_b, audio):
                path.write_bytes(b"test")
            content = {
                "duration": 2_000_000,
                "materials": {
                    "videos": [{"id": "v1", "path": str(video_a)}, {"id": "v2", "path": str(video_b)}],
                    "audios": [{"id": "a1", "path": str(audio)}],
                },
                "tracks": [
                    {
                        "type": "video",
                        "segments": [
                            {"material_id": "v1", "target_timerange": {"start": 0, "duration": 1_000_000}},
                            {"material_id": "v2", "target_timerange": {"start": 1_000_000, "duration": 1_000_000}},
                        ],
                    },
                    {
                        "type": "audio",
                        "segments": [{"material_id": "a1", "target_timerange": {"start": 0, "duration": 2_000_000}}],
                    },
                ],
            }
            (root / "draft_content.json").write_text(json.dumps(content), encoding="utf-8")
            self.assertTrue(validate_capcut_stage(root)["ok"])


if __name__ == "__main__":
    unittest.main()
