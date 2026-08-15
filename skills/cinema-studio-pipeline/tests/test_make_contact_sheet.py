import sys
import os
import struct
import tempfile
import unittest
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the implementation handles this path.
    Image = None


@unittest.skipIf(Image is None, "Pillow is not installed")
class MakeContactSheetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.frames = self.root / "frames"
        self.frames.mkdir()
        Image.new("RGB", (200, 100), "red").save(self.frames / "b.png")
        Image.new("RGB", (100, 200), "green").save(self.frames / "a.png")
        Image.new("RGB", (100, 100), "blue").save(self.frames / "달.png")
        self.output = self.root / "contact.png"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builds_a_deterministic_labeled_grid(self) -> None:
        from make_contact_sheet import make_contact_sheet

        result = make_contact_sheet(
            [self.frames],
            self.output,
            columns=2,
            thumb_size=(100, 60),
            padding=10,
            label_height=20,
            labels=True,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(["a.png", "b.png", "달.png"], [Path(path).name for path in result["inputs"]])
        with Image.open(self.output) as sheet:
            self.assertEqual((230, 190), sheet.size)

    def test_duplicate_basenames_are_ordered_by_their_full_paths(self) -> None:
        from make_contact_sheet import make_contact_sheet

        first_dir = self.root / "alpha"
        second_dir = self.root / "zulu"
        first_dir.mkdir()
        second_dir.mkdir()
        Image.new("RGB", (20, 20), "red").save(first_dir / "same.png")
        Image.new("RGB", (20, 20), "blue").save(second_dir / "same.png")

        result = make_contact_sheet([second_dir, first_dir], self.output)

        self.assertTrue(result["ok"], result)
        expected = sorted(
            [first_dir / "same.png", second_dir / "same.png"],
            key=lambda path: (path.name.casefold(), path.as_posix().casefold()),
        )
        self.assertEqual([str(path) for path in expected], result["inputs"])

    def test_fsyncs_the_rendered_sheet_before_atomic_publish(self) -> None:
        from _cinema_common import commit_temporary_file as real_commit
        from make_contact_sheet import make_contact_sheet

        events: list[str] = []

        def record_commit(temporary, target, *, force):
            events.append("commit")
            return real_commit(temporary, target, force=force)

        with patch(
            "make_contact_sheet.os.fsync",
            side_effect=lambda descriptor: events.append("fsync"),
        ), patch(
            "make_contact_sheet.commit_temporary_file", side_effect=record_commit
        ):
            result = make_contact_sheet([self.frames], self.output)

        self.assertTrue(result["ok"], result)
        self.assertEqual(["fsync", "commit"], events)

    def test_fsync_failure_never_publishes_a_contact_sheet(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with patch(
            "make_contact_sheet.os.fsync", side_effect=OSError("sync failed")
        ):
            result = make_contact_sheet([self.frames], self.output)

        self.assertFalse(result["ok"], result)
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob(".contact.*.tmp*")))

    def test_refuses_overwrite_without_force_and_force_is_explicit(self) -> None:
        from make_contact_sheet import make_contact_sheet

        self.output.write_bytes(b"keep")
        rejected = make_contact_sheet([self.frames], self.output)
        self.assertEqual("OUTPUT_EXISTS", rejected["errors"][0]["code"])
        self.assertEqual(b"keep", self.output.read_bytes())

        accepted = make_contact_sheet([self.frames], self.output, force=True)
        self.assertTrue(accepted["ok"], accepted)
        self.assertNotEqual(b"keep", self.output.read_bytes())

    def test_reports_missing_inputs_and_missing_pillow(self) -> None:
        from make_contact_sheet import make_contact_sheet

        empty = self.root / "empty"
        empty.mkdir()
        missing_inputs = make_contact_sheet([empty], self.output)
        self.assertEqual("NO_IMAGES", missing_inputs["errors"][0]["code"])

        with patch("make_contact_sheet.Image", None):
            missing_dependency = make_contact_sheet([self.frames], self.output)
        self.assertEqual("PILLOW_NOT_FOUND", missing_dependency["errors"][0]["code"])

    def test_rejects_invalid_or_oversized_layout_before_allocating_canvas(self) -> None:
        from make_contact_sheet import make_contact_sheet

        invalid_cases = [
            {"columns": True},
            {"columns": "4"},
            {"thumb_size": (320, "180")},
            {"thumb_size": (320,)},
            {"padding": False},
            {"label_height": -1},
            {"thumb_size": (100_000, 100_000)},
        ]
        for kwargs in invalid_cases:
            with self.subTest(kwargs=kwargs), patch(
                "make_contact_sheet.Image.new"
            ) as image_new:
                result = make_contact_sheet([self.frames], self.output, **kwargs)

            self.assertFalse(result["ok"], result)
            self.assertEqual("INVALID_LAYOUT", result["errors"][0]["code"])
            self.assertFalse(self.output.exists())
            image_new.assert_not_called()

    def test_canvas_allocation_failure_is_structured_and_does_not_publish(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with patch("make_contact_sheet.Image.new", side_effect=MemoryError("no memory")):
            result = make_contact_sheet([self.frames], self.output)

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_LAYOUT", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())

    def test_invalid_output_suffix_and_file_parent_are_structured_errors(self) -> None:
        from make_contact_sheet import make_contact_sheet

        invalid_suffix = self.root / "contact.unsupported"
        suffix_result = make_contact_sheet([self.frames], invalid_suffix)

        blocked_parent = self.root / "not-a-directory"
        blocked_parent.write_bytes(b"keep")
        parent_result = make_contact_sheet(
            [self.frames], blocked_parent / "contact.png"
        )

        self.assertFalse(suffix_result["ok"], suffix_result)
        self.assertEqual("OUTPUT_WRITE_FAILED", suffix_result["errors"][0]["code"])
        self.assertFalse(invalid_suffix.exists())
        self.assertFalse(parent_result["ok"], parent_result)
        self.assertEqual("OUTPUT_WRITE_FAILED", parent_result["errors"][0]["code"])
        self.assertEqual(b"keep", blocked_parent.read_bytes())

    def test_rejects_a_decompression_bomb_header_without_raising(self) -> None:
        from make_contact_sheet import make_contact_sheet

        def png_chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        huge = self.root / "huge.png"
        huge.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", 20000, 10000, 8, 2, 0, 0, 0),
            )
            + png_chunk(b"IEND", b"")
        )

        result = make_contact_sheet([huge], self.output)

        self.assertFalse(result["ok"], result)
        self.assertEqual("IMAGE_READ_FAILED", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())

    def test_has_one_non_force_winner_under_concurrency(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda _: make_contact_sheet(
                        [self.frames], self.output, columns=2, thumb_size=(64, 36), labels=False
                    ),
                    range(8),
                )
            )
        self.assertEqual(1, sum(result["ok"] for result in results), results)
        with Image.open(self.output) as sheet:
            sheet.verify()
        self.assertEqual([], list(self.root.glob(".contact.*.tmp*")))

    def test_rejects_output_aliasing_an_input_even_with_force(self) -> None:
        from make_contact_sheet import make_contact_sheet

        source = self.frames / "a.png"
        before = source.read_bytes()
        result = make_contact_sheet([source], source, force=True)
        self.assertIn("OUTPUT_ALIASES_INPUT", {item["code"] for item in result["errors"]})
        self.assertEqual(before, source.read_bytes())

    def test_rejects_a_hardlinked_output_alias_even_with_force(self) -> None:
        from make_contact_sheet import make_contact_sheet

        source = self.frames / "a.png"
        os.link(source, self.output)
        before = source.read_bytes()

        result = make_contact_sheet([source], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_INPUT", result["errors"][0]["code"])
        self.assertEqual(before, source.read_bytes())

    def test_rejects_a_name_redirecting_input_before_reading_images(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.frames,
        ), patch("make_contact_sheet.Image.open", wraps=Image.open) as image_open:
            result = make_contact_sheet([self.frames], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_INPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        image_open.assert_not_called()

    def test_rejects_a_name_redirecting_output_before_reading_images(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.output,
        ), patch("make_contact_sheet.Image.open", wraps=Image.open) as image_open:
            result = make_contact_sheet([self.frames], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_OUTPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        image_open.assert_not_called()

    def test_rejects_a_name_redirecting_image_discovered_in_a_directory(self) -> None:
        from make_contact_sheet import make_contact_sheet

        redirected_image = self.frames / "a.png"
        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == redirected_image,
        ), patch("make_contact_sheet.Image.open", wraps=Image.open) as image_open:
            result = make_contact_sheet([self.frames], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_INPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        image_open.assert_not_called()

    def test_rechecks_the_output_path_after_rendering_before_publish(self) -> None:
        from make_contact_sheet import make_contact_sheet

        redirect_active = False
        original_save = Image.Image.save

        def save_then_redirect(image, path, *args, **kwargs):
            nonlocal redirect_active
            result = original_save(image, path, *args, **kwargs)
            redirect_active = True
            return result

        def is_redirecting(path) -> bool:
            return redirect_active and Path(path) == self.output

        with patch.object(Image.Image, "save", new=save_then_redirect), patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=is_redirecting,
        ):
            result = make_contact_sheet([self.frames], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_OUTPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob(".contact.*.tmp*")))

    def test_rechecks_for_a_hardlink_alias_after_rendering_before_force_publish(self) -> None:
        from make_contact_sheet import make_contact_sheet

        source = self.frames / "a.png"
        before = source.read_bytes()
        original_save = Image.Image.save

        def save_then_plant_alias(image, path, *args, **kwargs):
            result = original_save(image, path, *args, **kwargs)
            os.link(source, self.output)
            return result

        with patch.object(Image.Image, "save", new=save_then_plant_alias):
            result = make_contact_sheet([source], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_INPUT", result["errors"][0]["code"])
        self.assertEqual(before, source.read_bytes())

    def test_rejects_a_name_redirecting_temporary_after_rendering(self) -> None:
        from make_contact_sheet import make_contact_sheet

        rendered_temporary: Path | None = None
        original_save = Image.Image.save

        def save_then_redirect_temporary(image, path, *args, **kwargs):
            nonlocal rendered_temporary
            result = original_save(image, path, *args, **kwargs)
            rendered_temporary = Path(path)
            return result

        def is_redirecting(path) -> bool:
            return rendered_temporary is not None and Path(path) == rendered_temporary

        with patch.object(Image.Image, "save", new=save_then_redirect_temporary), patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=is_redirecting,
        ):
            result = make_contact_sheet([self.frames], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_OUTPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())

    def test_rechecks_temporary_hardlink_after_fsync_before_publish(self) -> None:
        from make_contact_sheet import _output_error as real_output_error
        from make_contact_sheet import make_contact_sheet

        output_checks = 0
        source = self.frames / "a.png"
        unrelated = self.root / "unrelated.png"
        unrelated.write_bytes(source.read_bytes())

        def swap_temporary_after_fsync(raw_output, output, images, *, force):
            nonlocal output_checks
            output_checks += 1
            if output_checks == 2:
                temporary = next(self.root.glob(".contact.*.tmp.png"))
                temporary.unlink()
                os.link(unrelated, temporary)
            return real_output_error(raw_output, output, images, force=force)

        before = source.read_bytes()
        unrelated_before = unrelated.read_bytes()
        with patch(
            "make_contact_sheet._output_error",
            side_effect=swap_temporary_after_fsync,
        ):
            result = make_contact_sheet([source], self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertIn(
            result["errors"][0]["code"],
            {"OUTPUT_ALIASES_INPUT", "UNSAFE_OUTPUT_PATH"},
        )
        self.assertEqual(before, source.read_bytes())
        self.assertEqual(unrelated_before, unrelated.read_bytes())
        self.assertFalse(self.output.exists())

    def test_inaccessible_input_directory_returns_a_structured_discovery_error(self) -> None:
        from make_contact_sheet import make_contact_sheet

        with patch.object(Path, "iterdir", side_effect=PermissionError("offline folder")):
            result = make_contact_sheet([self.frames], self.output)

        self.assertFalse(result["ok"], result)
        self.assertEqual("INPUT_DISCOVERY_FAILED", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
