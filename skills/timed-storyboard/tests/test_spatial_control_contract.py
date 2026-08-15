import csv
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storyboard_plan.py"
SPEC = importlib.util.spec_from_file_location("storyboard_plan", SCRIPT)
assert SPEC and SPEC.loader
storyboard_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storyboard_plan)


class SpatialControlContractTests(unittest.TestCase):
    def test_depth_is_optional_but_must_be_normalized_when_present(self):
        errors: list[str] = []
        storyboard_plan.validate_path(
            [{"frame": 0, "x": 0.2, "y": 0.4, "depth": 1.2}],
            "shot.character",
            0,
            24,
            errors,
        )
        self.assertTrue(any("depth must be between 0 and 1" in item for item in errors))

        errors = []
        storyboard_plan.validate_path(
            [{"frame": 0, "x": 0.2, "y": 0.4}],
            "shot.character",
            0,
            24,
            errors,
        )
        self.assertEqual(errors, [])

        for invalid in (math.nan, math.inf, -math.inf):
            errors = []
            storyboard_plan.validate_path(
                [{"frame": 0, "x": invalid, "y": 0.4, "depth": invalid}],
                "shot.character",
                0,
                24,
                errors,
            )
            self.assertTrue(any("must be finite" in item for item in errors), errors)

    def test_waypoint_at_exclusive_shot_end_is_rejected(self):
        errors: list[str] = []
        storyboard_plan.validate_path(
            [{"frame": 24, "x": 0.2, "y": 0.4, "depth": 0.5}],
            "shot.character",
            0,
            24,
            errors,
        )
        self.assertTrue(any("[0, 24)" in item for item in errors), errors)

    def test_motion_path_export_preserves_depth_for_control_maps(self):
        plan = {
            "project": {"fps": 24},
            "shots": [
                {
                    "id": "S001",
                    "start_frame": 0,
                    "characters": [
                        {
                            "character_id": "hero",
                            "path": [
                                {
                                    "frame": 0,
                                    "x": 0.25,
                                    "y": 0.6,
                                    "depth": 0.8,
                                    "label": "start",
                                }
                            ],
                        }
                    ],
                    "props": [],
                    "camera": {"path": []},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            storyboard_plan.export_motion_paths(plan, output)
            with (output / "motion_paths.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["depth"], "0.8")


if __name__ == "__main__":
    unittest.main()
