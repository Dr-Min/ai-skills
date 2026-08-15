import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class ExtractReviewFramesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.media = self.root / "source video.mp4"
        self.media.write_bytes(b"source-must-not-change")
        self.ffmpeg = self.root / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        self.ffmpeg.write_bytes(b"test executable")
        self.ffmpeg.chmod(0o700)
        self.output = self.root / "review_frames"
        self.probe_patcher = patch(
            "extract_review_frames.inspect_media",
            return_value={
                "ok": True,
                "format": {"duration_seconds": 10.0},
                "video_streams": [{}],
            },
        )
        self.inspect = self.probe_patcher.start()

    def tearDown(self) -> None:
        self.probe_patcher.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def _ffmpeg_success(command, **kwargs):
        Path(command[-1]).write_bytes(b"png")
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_extracts_named_frames_without_mutating_source(self) -> None:
        from extract_review_frames import extract_review_frames

        before = self.media.read_bytes()
        with patch("extract_review_frames.subprocess.run", side_effect=self._ffmpeg_success) as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0, 1.25],
                ffmpeg_bin=self.ffmpeg,
                force=False,
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(before, self.media.read_bytes())
        self.assertEqual(
            ["frame_001_000000000ms.png", "frame_002_000001250ms.png"],
            [Path(path).name for path in result["frames"]],
        )
        first_command = run.call_args_list[0].args[0]
        self.assertIn("-n", first_command)
        self.assertIn("-frames:v", first_command)
        self.assertEqual(str(self.media.resolve()), first_command[first_command.index("-i") + 1])
        self.assertEqual(str(self.ffmpeg.resolve()), first_command[0])
        self.assertNotEqual(result["frames"][0], first_command[-1])
        self.assertEqual([], list(self.output.glob(".*.tmp.png")))

    def test_fsyncs_the_generated_frame_before_atomic_publish(self) -> None:
        from extract_review_frames import extract_review_frames
        from _cinema_common import commit_temporary_file as real_commit

        events: list[str] = []

        def record_commit(temporary, target, *, force):
            events.append("commit")
            return real_commit(temporary, target, force=force)

        with patch(
            "extract_review_frames.subprocess.run", side_effect=self._ffmpeg_success
        ), patch(
            "extract_review_frames.os.fsync",
            side_effect=lambda descriptor: events.append("fsync"),
        ), patch(
            "extract_review_frames.commit_temporary_file", side_effect=record_commit
        ):
            result = extract_review_frames(
                self.media, self.output, times=[0], ffmpeg_bin=self.ffmpeg
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual(["fsync", "commit"], events)

    def test_fsync_failure_never_publishes_a_frame(self) -> None:
        from extract_review_frames import extract_review_frames

        with patch(
            "extract_review_frames.subprocess.run", side_effect=self._ffmpeg_success
        ), patch(
            "extract_review_frames.os.fsync", side_effect=OSError("sync failed")
        ):
            result = extract_review_frames(
                self.media, self.output, times=[0], ffmpeg_bin=self.ffmpeg
            )

        target = self.output / "frame_001_000000000ms.png"
        self.assertFalse(result["ok"], result)
        self.assertFalse(target.exists())
        self.assertEqual([], list(self.output.glob(".*.tmp.png")))

    def test_refuses_to_overwrite_an_existing_frame_without_force(self) -> None:
        from extract_review_frames import extract_review_frames

        self.output.mkdir()
        existing = self.output / "frame_001_000000000ms.png"
        existing.write_bytes(b"keep-me")
        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media, self.output, times=[0], ffmpeg_bin=self.ffmpeg
            )

        self.assertFalse(result["ok"])
        self.assertEqual("FRAME_EXISTS", result["errors"][0]["code"])
        self.assertEqual(b"keep-me", existing.read_bytes())
        run.assert_not_called()

    def test_force_is_explicit_and_count_uses_probed_duration(self) -> None:
        from extract_review_frames import extract_review_frames

        self.output.mkdir()
        existing = self.output / "frame_001_000001000ms.png"
        existing.write_bytes(b"old")
        probe_result = {
            "ok": True,
            "format": {"duration_seconds": 6.0},
            "video_streams": [{}],
        }
        with patch("extract_review_frames.inspect_media", return_value=probe_result), patch(
            "extract_review_frames.subprocess.run", side_effect=self._ffmpeg_success
        ) as run:
            result = extract_review_frames(
                self.media,
                self.output,
                count=3,
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual([1.0, 3.0, 5.0], result["times_seconds"])
        first_command = run.call_args_list[0].args[0]
        self.assertIn("-n", first_command)
        self.assertNotIn("-y", first_command)
        self.assertNotEqual(str(existing), first_command[-1])
        self.assertEqual(b"png", existing.read_bytes())

    def test_force_rejects_a_target_that_aliases_the_source(self) -> None:
        from extract_review_frames import extract_review_frames

        self.output.mkdir()
        target = self.output / "frame_001_000000000ms.png"
        os.link(self.media, target)
        before = self.media.read_bytes()
        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_SOURCE", result["errors"][0]["code"])
        self.assertEqual(before, self.media.read_bytes())
        run.assert_not_called()

    def test_force_rejects_a_preseeded_frame_symlink(self) -> None:
        from extract_review_frames import extract_review_frames

        self.output.mkdir()
        external = self.root / "external.png"
        external.write_bytes(b"external-must-not-change")
        target = self.output / "frame_001_000000000ms.png"
        try:
            target.symlink_to(external)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_FRAME_TARGET", result["errors"][0]["code"])
        self.assertEqual(b"external-must-not-change", external.read_bytes())
        run.assert_not_called()

    def test_rejects_a_name_redirecting_media_path_before_running_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.media,
        ), patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_MEDIA_PATH", result["errors"][0]["code"])
        run.assert_not_called()

    def test_rejects_a_name_redirecting_output_directory_before_running_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.output,
        ), patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_FRAME_TARGET", result["errors"][0]["code"])
        run.assert_not_called()

    def test_non_force_concurrency_has_one_atomic_publish_winner(self) -> None:
        from extract_review_frames import extract_review_frames

        barrier = threading.Barrier(2)

        def simultaneous_ffmpeg(command, **kwargs):
            barrier.wait(timeout=5)
            Path(command[-1]).write_bytes(b"png")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch(
            "extract_review_frames.subprocess.run", side_effect=simultaneous_ffmpeg
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _: extract_review_frames(
                            self.media,
                            self.output,
                            times=[0],
                            ffmpeg_bin=self.ffmpeg,
                        ),
                        range(2),
                    )
                )

        self.assertEqual(1, sum(result["ok"] is True for result in results), results)
        self.assertEqual(b"png", (self.output / "frame_001_000000000ms.png").read_bytes())
        self.assertEqual([], list(self.output.glob(".*.tmp.png")))

    def test_invalid_times_and_missing_ffmpeg_are_graceful(self) -> None:
        from extract_review_frames import extract_review_frames

        invalid = extract_review_frames(self.media, self.output, times=[-0.1])
        self.assertEqual("INVALID_TIME", invalid["errors"][0]["code"])
        with patch.dict(os.environ, {"PATH": ""}):
            missing = extract_review_frames(self.media, self.output, times=[0])
        self.assertEqual("FFMPEG_NOT_FOUND", missing["errors"][0]["code"])

    def test_stops_consuming_after_one_hundred_explicit_times(self) -> None:
        from extract_review_frames import extract_review_frames

        def guarded_times():
            for index in range(101):
                yield index / 100
            raise AssertionError("explicit time iterable was consumed without a bound")

        self.inspect.reset_mock()
        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=guarded_times(),
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_COUNT", result["errors"][0]["code"])
        self.inspect.assert_not_called()
        run.assert_not_called()

    def test_rejects_explicit_times_beyond_the_probed_duration(self) -> None:
        from extract_review_frames import extract_review_frames

        probe_result = {
            "ok": True,
            "format": {"duration_seconds": 2.0},
            "video_streams": [{}],
        }
        with patch(
            "extract_review_frames.inspect_media", return_value=probe_result
        ) as inspect, patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[2.001],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_TIME", result["errors"][0]["code"])
        inspect.assert_called_once_with(self.media.resolve(), ffprobe_bin=None)
        run.assert_not_called()

    def test_rejects_explicit_time_that_could_expand_the_frame_filename(self) -> None:
        from extract_review_frames import extract_review_frames

        self.inspect.reset_mock()
        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=["1e1000000"],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_TIME", result["errors"][0]["code"])
        self.inspect.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_rejects_oversized_time_tokens_before_decimal_parsing(self) -> None:
        from extract_review_frames import extract_review_frames

        self.inspect.reset_mock()
        with patch(
            "extract_review_frames.Decimal",
            side_effect=AssertionError("oversized token reached Decimal"),
        ) as decimal_constructor, patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=["1" * 65],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_TIME", result["errors"][0]["code"])
        decimal_constructor.assert_not_called()
        self.inspect.assert_not_called()
        run.assert_not_called()

    def test_duplicate_times_are_rejected_before_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        with patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[1, 1.0004],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("DUPLICATE_FRAME_TIME", result["errors"][0]["code"])
        run.assert_not_called()

    def test_non_finite_probed_duration_fails_closed_before_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        probe_result = {
            "ok": True,
            "format": {"duration_seconds": float("nan")},
            "video_streams": [{}],
        }
        with patch(
            "extract_review_frames.inspect_media", return_value=probe_result
        ), patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                count=3,
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("DURATION_UNKNOWN", result["errors"][0]["code"])
        run.assert_not_called()

    def test_failed_ffmpeg_cleans_its_unique_temporary_output(self) -> None:
        from extract_review_frames import extract_review_frames

        def failed_after_write(command, **kwargs):
            Path(command[-1]).write_bytes(b"partial")
            return subprocess.CompletedProcess(command, 1, "", "decode failed")

        with patch(
            "extract_review_frames.subprocess.run", side_effect=failed_after_write
        ):
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertFalse((self.output / "frame_001_000000000ms.png").exists())
        self.assertEqual([], list(self.output.glob(".*.tmp.png")))

    def test_stops_ffmpeg_while_diagnostic_output_exceeds_the_safe_limit(self) -> None:
        from extract_review_frames import extract_review_frames

        class EmptyBytes:
            def read(self, size: int) -> bytes:
                return b""

            def close(self) -> None:
                pass

        class EndlessBytes:
            def __init__(self) -> None:
                self.total_read = 0

            def read(self, size: int) -> bytes:
                self.total_read += size
                return b"e" * size

            def close(self) -> None:
                pass

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = EmptyBytes()
                self.stderr = EndlessBytes()
                self.returncode: int | None = None
                self.killed = False

            def wait(self, timeout=None) -> int:
                self.returncode = -9 if self.killed else 0
                return self.returncode

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

        process = FakeProcess()
        with patch(
            "extract_review_frames.MAX_FFMPEG_STDERR_BYTES", 32, create=True
        ), patch(
            "extract_review_frames.subprocess.Popen", return_value=process
        ) as popen:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFMPEG_FAILED", result["errors"][0]["code"])
        self.assertTrue(process.killed)
        self.assertLessEqual(process.stderr.total_read, 33)
        popen.assert_called_once()
        self.assertEqual([], list(self.output.glob(".*.tmp.png")))

    def test_rejects_an_ffmpeg_temporary_file_hardlinked_to_the_source(self) -> None:
        from extract_review_frames import extract_review_frames

        def hardlink_source_as_temporary(command, **kwargs):
            os.link(self.media, Path(command[-1]))
            return subprocess.CompletedProcess(command, 0, "", "")

        before = self.media.read_bytes()
        with patch(
            "extract_review_frames.subprocess.run",
            side_effect=hardlink_source_as_temporary,
        ):
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_SOURCE", result["errors"][0]["code"])
        self.assertEqual(before, self.media.read_bytes())
        self.assertFalse((self.output / "frame_001_000000000ms.png").exists())

    def test_rechecks_temporary_alias_after_fsync_before_publish(self) -> None:
        from extract_review_frames import _target_error as real_target_error
        from extract_review_frames import extract_review_frames

        target_checks = 0

        def swap_after_fsync(source, target, *, force):
            nonlocal target_checks
            target_checks += 1
            if target_checks == 2:
                temporary = next(self.output.glob(".*.tmp.png"))
                temporary.unlink()
                os.link(self.media, temporary)
            return real_target_error(source, target, force=force)

        before = self.media.read_bytes()
        with patch(
            "extract_review_frames.subprocess.run", side_effect=self._ffmpeg_success
        ), patch(
            "extract_review_frames._target_error", side_effect=swap_after_fsync
        ):
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertIn(
            result["errors"][0]["code"],
            {"OUTPUT_ALIASES_SOURCE", "UNSAFE_FRAME_TARGET"},
        )
        self.assertEqual(before, self.media.read_bytes())
        self.assertFalse((self.output / "frame_001_000000000ms.png").exists())

    def test_rechecks_the_output_path_after_ffmpeg_before_publishing(self) -> None:
        from extract_review_frames import extract_review_frames

        redirect_active = False

        def ffmpeg_then_redirect(command, **kwargs):
            nonlocal redirect_active
            Path(command[-1]).write_bytes(b"png")
            redirect_active = True
            return subprocess.CompletedProcess(command, 0, "", "")

        def is_redirecting(path) -> bool:
            return redirect_active and Path(path) == self.output

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=is_redirecting,
        ), patch(
            "extract_review_frames.subprocess.run",
            side_effect=ffmpeg_then_redirect,
        ):
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_FRAME_TARGET", result["errors"][0]["code"])
        self.assertFalse((self.output / "frame_001_000000000ms.png").exists())

    def test_rechecks_each_frame_target_before_running_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        redirect_active = False

        def resolve_then_redirect(command, explicit=None):
            nonlocal redirect_active
            redirect_active = True
            return self.ffmpeg

        def is_redirecting(path) -> bool:
            return redirect_active and Path(path) == self.output

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=is_redirecting,
        ), patch(
            "extract_review_frames.resolve_trusted_executable",
            side_effect=resolve_then_redirect,
        ), patch("extract_review_frames.subprocess.run") as run:
            result = extract_review_frames(
                self.media,
                self.output,
                times=[0],
                ffmpeg_bin=self.ffmpeg,
                force=True,
            )

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_FRAME_TARGET", result["errors"][0]["code"])
        run.assert_not_called()

    def test_default_search_ignores_a_planted_current_directory_ffmpeg(self) -> None:
        from extract_review_frames import extract_review_frames

        original_cwd = Path.cwd()
        search_path = os.pathsep.join(("", ".", str(self.root)))
        try:
            os.chdir(self.root)
            with patch.dict(
                os.environ,
                {"PATH": search_path, "PATHEXT": ".EXE"},
            ), patch("extract_review_frames.subprocess.run") as run:
                result = extract_review_frames(self.media, self.output, times=[0])
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFMPEG_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
