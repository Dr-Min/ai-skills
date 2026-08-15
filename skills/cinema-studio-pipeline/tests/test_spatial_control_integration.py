import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SpatialControlIntegrationTests(unittest.TestCase):
    def test_shot_review_collects_packet_and_both_control_maps(self) -> None:
        from prepare_review import _supporting_evidence

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            still = root / "05_shots" / "S01_SH010" / "still.png"
            review_map = root / "control-maps" / "review" / "S01_SH010.png"
            clean_map = root / "control-maps" / "clean" / "S01_SH010.png"
            packet_path = root / "control-maps" / "packets" / "S01_SH010.json"
            for path, content in (
                (still, b"still"),
                (review_map, b"review-map"),
                (clean_map, b"clean-map"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            packet = {
                "schema_version": "1.0",
                "shot_id": "S01_SH010",
                "structural_scope_only": True,
                "outputs": {
                    "review_map": {
                        "path": review_map.relative_to(root).as_posix(),
                        "sha256": digest(review_map),
                    },
                    "clean_map": {
                        "path": clean_map.relative_to(root).as_posix(),
                        "sha256": digest(clean_map),
                    },
                },
            }
            packet_path.parent.mkdir(parents=True, exist_ok=True)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            shot = {
                "shot_id": "S01_SH010",
                "still_evidence": [
                    {
                        "role": "STILL",
                        "path": still.relative_to(root).as_posix(),
                        "sha256": digest(still),
                    }
                ],
                "spatial": {
                    "control_packet": {
                        "path": packet_path.relative_to(root).as_posix(),
                        "sha256": digest(packet_path),
                    }
                },
            }

            evidence = _supporting_evidence(root, {"project_id": "p"}, "SHOT_STILL", shot, ())
            relpaths = {path.relative_to(root).as_posix() for path, _ in evidence}
            self.assertEqual(
                relpaths,
                {
                    still.relative_to(root).as_posix(),
                    packet_path.relative_to(root).as_posix(),
                    review_map.relative_to(root).as_posix(),
                    clean_map.relative_to(root).as_posix(),
                },
            )

            clean_map.write_bytes(b"changed-after-packet")
            with self.assertRaisesRegex(ValueError, "hash"):
                _supporting_evidence(root, {"project_id": "p"}, "SHOT_STILL", shot, ())


if __name__ == "__main__":
    unittest.main()
