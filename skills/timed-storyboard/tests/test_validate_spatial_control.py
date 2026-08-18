import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
import struct
import zlib
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_spatial_control.py"
SPEC = importlib.util.spec_from_file_location("validate_spatial_control", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_png(path: Path, width: int, height: int, pixels=None) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    pixels = pixels or {}
    rows = b""
    for y in range(height):
        row = b"".join(bytes(pixels.get((x, y), (0, 0, 0))) for x in range(width))
        rows += b"\x00" + row
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


class SpatialControlValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan_path = self.root / "storyboard_plan.json"
        self.plan = {
            "schema_version": "1.0",
            "project": {"aspect_ratio": "16:9"},
            "shots": [{"id": "S001", "start_frame": 0, "end_frame": 96}],
        }
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.review_map = self.root / "control-maps" / "review" / "S001-spatial-review.png"
        self.clean_map = self.root / "control-maps" / "clean" / "S001-spatial-clean.png"
        self.review_map.parent.mkdir(parents=True)
        self.clean_map.parent.mkdir(parents=True)
        write_png(self.review_map, 20, 20)
        write_png(
            self.clean_map,
            16,
            9,
            {(1, 1): (0x6B, 0x8E, 0x9E), (14, 7): (0xA1, 0x7C, 0x6B)},
        )
        self.packet_path = self.root / "control-maps" / "packets" / "S001-spatial-control.json"
        self.packet_path.parent.mkdir(parents=True)
        self.packet = {
            "schema_version": "1.0",
            "source_plan": {"path": "storyboard_plan.json", "sha256": digest(self.plan_path)},
            "shot_id": "S001",
            "aspect_ratio": "16:9",
            "clean_map_background_color": "#000000",
            "frame_range": {"start_frame": 0, "end_frame": 96},
            "coordinate_system": {
                "screen_origin": "TOP_LEFT",
                "x_range": [0, 1],
                "y_range": [0, 1],
                "depth_range": [0, 1],
                "depth_meaning": "0_NEAREST_CAMERA_1_FARTHEST_PLAYABLE_SPACE",
            },
            "camera": {"axis_side": "south of dialogue axis", "path": []},
            "entities": [
                {
                    "entity_id": "woman",
                    "role": "CHARACTER",
                    "color": "#6B8E9E",
                    "states": [
                        {
                            "frame": 0,
                            "x": 0.25,
                            "y": 0.6,
                            "depth": 0.4,
                            "body_facing": "frame-right",
                            "head_facing": "frame-right",
                            "gaze_target_id": "man",
                            "pose_or_action_state": "seated and listening",
                            "occluded_by_entity_ids": [],
                        }
                    ],
                },
                {
                    "entity_id": "man",
                    "role": "CHARACTER",
                    "color": "#A17C6B",
                    "states": [
                        {
                            "frame": 0,
                            "x": 0.7,
                            "y": 0.6,
                            "depth": 0.45,
                            "body_facing": "frame-left",
                            "head_facing": "frame-left",
                            "gaze_target_id": "woman",
                            "pose_or_action_state": "seated and speaking",
                            "occluded_by_entity_ids": [],
                        }
                    ],
                },
            ],
            "events": [],
            "inferred_fields": [],
            "assumptions": [],
            "failure_conditions": ["screen side flips"],
            "outputs": {
                "review_map": {
                    "path": self.review_map.relative_to(self.root).as_posix(),
                    "sha256": digest(self.review_map),
                },
                "clean_map": {
                    "path": self.clean_map.relative_to(self.root).as_posix(),
                    "sha256": digest(self.clean_map),
                },
            },
            "structural_scope_only": True,
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_packet(self, packet=None):
        payload = self.packet if packet is None else packet
        self.packet_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_accepts_exact_hash_bound_packet(self):
        self.write_packet()
        result = validator.validate_packet(self.root, self.packet_path)
        self.assertTrue(result["ok"], result)
        self.assertIn("storyboard_plan.json", result["checked_files"])

    def test_rejects_placeholders_false_scope_path_escape_and_hash_mismatch(self):
        packet = copy.deepcopy(self.packet)
        packet["camera"]["axis_side"] = "REPLACE_WITH_SIDE"
        packet["structural_scope_only"] = False
        packet["outputs"]["review_map"]["path"] = "../outside.png"
        packet["outputs"]["clean_map"]["sha256"] = "0" * 64
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        joined = "\n".join(result["errors"])
        self.assertFalse(result["ok"])
        self.assertIn("placeholder", joined)
        self.assertIn("structural_scope_only", joined)
        self.assertIn("unsafe project-relative path", joined)
        self.assertIn("does not match actual bytes", joined)

    def test_rejects_duplicate_ids_colors_unknown_links_and_out_of_range_points(self):
        packet = copy.deepcopy(self.packet)
        packet["entities"][1]["entity_id"] = "woman"
        packet["entities"][1]["color"] = "#6b8e9e"
        packet["entities"][0]["states"][0]["depth"] = 1.2
        packet["entities"][0]["states"][0]["gaze_target_id"] = "missing"
        packet["events"] = [
            {
                "event_id": "EV1",
                "type": "CONTACT",
                "frame": 96,
                "participant_entity_ids": ["missing"],
            }
        ]
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        joined = "\n".join(result["errors"])
        self.assertIn("entity_id is duplicated", joined)
        self.assertIn("color is duplicated", joined)
        self.assertIn("between 0 and 1", joined)
        self.assertIn("gaze_target_id is unknown", joined)
        self.assertIn("must be inside [0, 96)", joined)

    def test_rejects_packet_that_does_not_match_plan_shot(self):
        packet = copy.deepcopy(self.packet)
        packet["frame_range"]["end_frame"] = 95
        packet["aspect_ratio"] = "9:16"
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        joined = "\n".join(result["errors"])
        self.assertIn("frame_range must exactly match", joined)
        self.assertIn("aspect_ratio must exactly match", joined)

    def test_schema_rejects_unknown_fields_and_duplicate_links(self):
        packet = copy.deepcopy(self.packet)
        packet["style"] = "must not enter structural packet"
        packet["entities"][0]["states"][0]["unexpected"] = True
        packet["entities"][0]["states"][0]["occluded_by_entity_ids"] = ["man", "man"]
        packet["events"] = [
            {
                "event_id": "EV1",
                "type": "CONTACT",
                "frame": 10,
                "participant_entity_ids": ["woman", "woman"],
            }
        ]
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        joined = "\n".join(result["errors"])
        self.assertFalse(result["ok"])
        self.assertIn("Additional properties are not allowed", joined)
        self.assertIn("has non-unique elements", joined)

    def test_rejects_corrupt_png_and_wrong_clean_map_aspect(self):
        packet = copy.deepcopy(self.packet)
        self.review_map.write_bytes(b"not-a-png")
        write_png(self.clean_map, 10, 10)
        packet["outputs"]["review_map"]["sha256"] = digest(self.review_map)
        packet["outputs"]["clean_map"]["sha256"] = digest(self.clean_map)
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        joined = "\n".join(result["errors"])
        self.assertIn("not a valid PNG", joined)
        self.assertIn("must exactly match the packet aspect_ratio", joined)

    def test_rejects_clean_map_colors_outside_declared_geometry_palette(self):
        packet = copy.deepcopy(self.packet)
        write_png(
            self.clean_map,
            16,
            9,
            {
                (1, 1): (0x6B, 0x8E, 0x9E),
                (14, 7): (0xA1, 0x7C, 0x6B),
                (8, 4): (0xFF, 0x00, 0xFF),
            },
        )
        packet["outputs"]["clean_map"]["sha256"] = digest(self.clean_map)
        self.write_packet(packet)
        result = validator.validate_packet(self.root, self.packet_path)
        self.assertFalse(result["ok"], result)
        self.assertIn("undeclared color", "\n".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
