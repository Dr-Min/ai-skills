import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class InspectMediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.media = self.root / "달 장면.mp4"
        self.media.write_bytes(b"placeholder")
        self.ffprobe = self.root / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        self.ffprobe.write_bytes(b"test executable")
        self.ffprobe.chmod(0o700)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_returns_normalized_video_and_audio_metadata(self) -> None:
        payload = {
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "4.250000",
                "size": "123456",
                "bit_rate": "987654",
            },
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "24000/1001",
                    "avg_frame_rate": "24000/1001",
                    "pix_fmt": "yuv420p",
                    "bit_rate": "8000000",
                    "nb_frames": "102",
                    "color_space": "bt709",
                    "color_transfer": "bt709",
                    "color_primaries": "bt709",
                    "duration": "4.25",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "duration": "4.25",
                },
            ],
        }
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        from inspect_media import inspect_media

        with patch("inspect_media.subprocess.run", return_value=completed) as run:
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

        self.assertTrue(result["ok"], result)
        self.assertEqual(4.25, result["format"]["duration_seconds"])
        self.assertEqual("24000/1001", result["video_streams"][0]["frame_rate"])
        self.assertAlmostEqual(23.976023976, result["video_streams"][0]["fps"], places=6)
        self.assertEqual(102, result["video_streams"][0]["frame_count"])
        self.assertEqual("bt709", result["video_streams"][0]["color_space"])
        self.assertEqual(48000, result["audio_streams"][0]["sample_rate_hz"])
        command = run.call_args.args[0]
        self.assertIn("-show_format", command)
        self.assertIn("-show_streams", command)
        entries = command[command.index("-show_entries") + 1]
        for field in (
            "bit_rate",
            "nb_frames",
            "color_space",
            "color_transfer",
            "color_primaries",
        ):
            self.assertIn(field, entries)
        self.assertEqual(str(self.ffprobe.resolve()), command[0])
        self.assertEqual(str(self.media.resolve()), command[-1])

    def test_nonfinite_ffprobe_json_is_rejected(self) -> None:
        from inspect_media import inspect_media

        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"format":{"duration":NaN,"size":Infinity},"streams":[]}',
            stderr="",
        )
        with patch("inspect_media.subprocess.run", return_value=completed):
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_INVALID_JSON", result["errors"][0]["code"])

    def test_bounded_ffprobe_json_parser_rejects_oversized_deep_and_giant_values(self) -> None:
        from inspect_media import MAX_FFPROBE_JSON_BYTES, inspect_media

        malformed = (
            "{" * 1200 + "null" + "}" * 1200,
            '{"format":{"size":' + "9" * 5000 + '},"streams":[]}',
            " " * (MAX_FFPROBE_JSON_BYTES + 1),
        )
        for stdout in malformed:
            with self.subTest(prefix=stdout[:20]), patch(
                "inspect_media.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=stdout, stderr=""
                ),
            ):
                result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

            self.assertFalse(result["ok"], result)
            self.assertEqual("FFPROBE_INVALID_JSON", result["errors"][0]["code"])

    def test_stops_ffprobe_while_stdout_exceeds_the_safe_limit(self) -> None:
        from inspect_media import inspect_media

        class EndlessBytes:
            def __init__(self) -> None:
                self.total_read = 0

            def read(self, size: int) -> bytes:
                self.total_read += size
                return b"x" * size

            def close(self) -> None:
                pass

        class EmptyBytes:
            def read(self, size: int) -> bytes:
                return b""

            def close(self) -> None:
                pass

        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = EndlessBytes()
                self.stderr = EmptyBytes()
                self.returncode: int | None = None
                self.killed = False

            def wait(self, timeout=None) -> int:
                self.returncode = -9 if self.killed else 0
                return self.returncode

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

        process = FakeProcess()
        with patch("inspect_media.MAX_FFPROBE_JSON_BYTES", 32), patch(
            "inspect_media.subprocess.Popen", return_value=process
        ) as popen:
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_INVALID_JSON", result["errors"][0]["code"])
        self.assertTrue(process.killed)
        self.assertLessEqual(process.stdout.total_read, 33)
        popen.assert_called_once()

    def test_oversized_or_nonfinite_frame_rates_are_normalized_to_unknown(self) -> None:
        from inspect_media import _fps

        self.assertIsNone(_fps(f"{10 ** 400}/1"))
        self.assertIsNone(_fps("1/" + str(10 ** 400)))

    def test_missing_ffprobe_returns_a_graceful_dependency_error(self) -> None:
        from inspect_media import inspect_media

        with patch.dict(os.environ, {"PATH": ""}):
            result = inspect_media(self.media)

        self.assertFalse(result["ok"])
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])

    def test_missing_input_and_probe_failure_do_not_raise(self) -> None:
        from inspect_media import inspect_media

        missing = inspect_media(Path(self.temp_dir.name) / "missing.mp4")
        self.assertEqual("MEDIA_NOT_FOUND", missing["errors"][0]["code"])

        failed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="invalid media"
        )
        with patch("inspect_media.subprocess.run", return_value=failed):
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)
        self.assertEqual("FFPROBE_FAILED", result["errors"][0]["code"])

    def test_default_search_ignores_empty_relative_and_current_directory_entries(self) -> None:
        from inspect_media import inspect_media

        original_cwd = Path.cwd()
        search_path = os.pathsep.join(("", ".", str(self.root)))
        try:
            os.chdir(self.root)
            with patch.dict(
                os.environ,
                {"PATH": search_path, "PATHEXT": ".EXE"},
            ), patch("inspect_media.subprocess.run") as run:
                result = inspect_media(self.media)
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    def test_default_search_uses_an_absolute_regular_path_entry(self) -> None:
        from inspect_media import inspect_media

        tools_dir = self.root / "trusted-tools"
        tools_dir.mkdir()
        trusted = tools_dir / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        trusted.write_bytes(b"trusted executable")
        trusted.chmod(0o700)
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"format": {}, "streams": []}), stderr=""
        )
        search_path = os.pathsep.join(("relative-tools", str(tools_dir)))

        with patch.dict(
            os.environ,
            {"PATH": search_path, "PATHEXT": ".EXE"},
        ), patch("inspect_media.subprocess.run", return_value=completed) as run:
            result = inspect_media(self.media)

        self.assertTrue(result["ok"], result)
        self.assertEqual(
            os.path.normcase(str(trusted.resolve())),
            os.path.normcase(run.call_args.args[0][0]),
        )

    def test_default_search_rejects_a_path_directory_below_the_working_directory(self) -> None:
        from inspect_media import inspect_media

        working_directory = self.root / "workspace"
        tools_dir = working_directory / "tools"
        tools_dir.mkdir(parents=True)
        planted = tools_dir / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        planted.write_bytes(b"planted executable")
        planted.chmod(0o700)
        original_cwd = Path.cwd()
        try:
            os.chdir(working_directory)
            with patch.dict(
                os.environ,
                {"PATH": str(tools_dir), "PATHEXT": ".EXE"},
            ), patch("inspect_media.subprocess.run") as run:
                result = inspect_media(self.media)
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows extended paths are Windows-specific")
    def test_default_search_rejects_extended_namespace_cwd_descendant(self) -> None:
        from inspect_media import inspect_media

        working_directory = self.root / "extended-workspace"
        tools_dir = working_directory / "tools"
        tools_dir.mkdir(parents=True)
        planted = tools_dir / "ffprobe.exe"
        planted.write_bytes(b"planted executable")
        planted.chmod(0o700)
        extended_tools = "\\\\?\\" + str(tools_dir.resolve())
        original_cwd = Path.cwd()
        try:
            os.chdir(working_directory)
            with patch.dict(
                os.environ,
                {"PATH": extended_tools, "PATHEXT": ".EXE"},
            ), patch("inspect_media.subprocess.run") as run:
                result = inspect_media(self.media)
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows path identity aliases are Windows-specific")
    def test_default_search_rejects_a_cwd_descendant_by_file_identity(self) -> None:
        from inspect_media import inspect_media

        working_directory = self.root / "identity-workspace"
        working_directory.mkdir()
        alias_root = self.root / "identity-alias"
        tools_dir = alias_root / "tools"
        tools_dir.mkdir(parents=True)
        planted = tools_dir / "ffprobe.exe"
        planted.write_bytes(b"planted executable")
        planted.chmod(0o700)
        real_samefile = os.path.samefile

        def samefile_with_alias(left, right):
            if Path(left) == alias_root and Path(right) == working_directory:
                return True
            return real_samefile(left, right)

        original_cwd = Path.cwd()
        try:
            os.chdir(working_directory)
            with patch.dict(
                os.environ,
                {"PATH": str(tools_dir), "PATHEXT": ".EXE"},
            ), patch(
                "inspect_media.os.path.samefile", side_effect=samefile_with_alias
            ), patch("inspect_media.subprocess.run") as run:
                result = inspect_media(self.media)
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows administrative shares are Windows-specific")
    def test_default_search_rejects_a_local_unc_alias_of_cwd_descendant(self) -> None:
        from inspect_media import inspect_media

        working_directory = self.root / "unc-workspace"
        tools_dir = working_directory / "tools"
        tools_dir.mkdir(parents=True)
        planted = tools_dir / "ffprobe.exe"
        planted.write_bytes(b"planted executable")
        planted.chmod(0o700)
        drive, tail = os.path.splitdrive(str(tools_dir.resolve()))
        unc_tools = Path(
            "\\\\localhost\\" + drive[0] + "$\\" + tail.lstrip("\\/")
        )
        if not unc_tools.is_dir():
            self.skipTest("localhost administrative share is unavailable")
        self.assertTrue(os.path.samefile(unc_tools, tools_dir))

        original_cwd = Path.cwd()
        try:
            os.chdir(working_directory)
            with patch.dict(
                os.environ,
                {"PATH": str(unc_tools), "PATHEXT": ".EXE"},
            ), patch("inspect_media.subprocess.run") as run:
                result = inspect_media(self.media)
        finally:
            os.chdir(original_cwd)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "PATHEXT script lookup is Windows-specific")
    def test_default_search_rejects_batch_and_command_candidates(self) -> None:
        from inspect_media import inspect_media

        scripts_dir = self.root / "script-tools"
        scripts_dir.mkdir()
        for suffix in (".bat", ".cmd"):
            candidate = scripts_dir / f"ffprobe{suffix}"
            candidate.write_text("@exit /b 0\n", encoding="utf-8")
            candidate.chmod(0o700)

        with patch.dict(
            os.environ,
            {"PATH": str(scripts_dir), "PATHEXT": ".BAT;.CMD"},
        ), patch("inspect_media.subprocess.run") as run:
            result = inspect_media(self.media)

        self.assertFalse(result["ok"], result)
        self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
        run.assert_not_called()

    def test_explicit_probe_rejects_non_files_and_reparse_points(self) -> None:
        from inspect_media import inspect_media

        directory_result = inspect_media(self.media, ffprobe_bin=self.root)
        self.assertEqual("FFPROBE_NOT_FOUND", directory_result["errors"][0]["code"])

        link = self.root / ("linked-ffprobe.exe" if os.name == "nt" else "linked-ffprobe")
        try:
            link.symlink_to(self.ffprobe)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with patch("inspect_media.subprocess.run") as run:
            linked_result = inspect_media(self.media, ffprobe_bin=link)
        self.assertEqual("FFPROBE_NOT_FOUND", linked_result["errors"][0]["code"])
        run.assert_not_called()

    def test_cloud_reparse_metadata_is_not_treated_as_name_redirection(self) -> None:
        from inspect_media import is_reparse_path

        cloud_metadata = SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            st_reparse_tag=0x9000001A,
        )
        with patch("_cinema_common.os.lstat", return_value=cloud_metadata):
            self.assertFalse(is_reparse_path(self.media))

    def test_explicit_probe_rejects_batch_and_command_scripts(self) -> None:
        from inspect_media import inspect_media

        for suffix in (".bat", ".cmd"):
            with self.subTest(suffix=suffix):
                script = self.root / f"ffprobe{suffix}"
                script.write_text("@exit /b 0\n", encoding="utf-8")
                script.chmod(0o700)
                with patch("inspect_media.subprocess.run") as run:
                    result = inspect_media(self.media, ffprobe_bin=script)

                self.assertFalse(result["ok"], result)
                self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
                run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Win32 trailing-name normalization is Windows-specific")
    def test_explicit_probe_rejects_trailing_dot_or_space_command_alias(self) -> None:
        from inspect_media import inspect_media

        script = self.root / "ffprobe.cmd"
        script.write_text("@exit /b 0\n", encoding="utf-8")
        script.chmod(0o700)
        for disguised in (Path(f"{script}."), Path(f"{script} ")):
            with self.subTest(path=str(disguised)), patch(
                "inspect_media.subprocess.run"
            ) as run:
                result = inspect_media(self.media, ffprobe_bin=disguised)
            self.assertFalse(result["ok"], result)
            self.assertEqual("FFPROBE_NOT_FOUND", result["errors"][0]["code"])
            run.assert_not_called()

    def test_explicit_absolute_probe_remains_allowed_below_the_working_directory(self) -> None:
        from inspect_media import inspect_media

        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps({"format": {}, "streams": []}), stderr=""
        )
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with patch("inspect_media.subprocess.run", return_value=completed) as run:
                result = inspect_media(self.media, ffprobe_bin=self.ffprobe.resolve())
        finally:
            os.chdir(original_cwd)

        self.assertTrue(result["ok"], result)
        self.assertEqual(
            os.path.normcase(str(self.ffprobe.resolve())),
            os.path.normcase(run.call_args.args[0][0]),
        )

    def test_rejects_a_media_symlink_before_running_ffprobe(self) -> None:
        from inspect_media import inspect_media

        linked_media = self.root / "linked-media.mp4"
        try:
            linked_media.symlink_to(self.media)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with patch("inspect_media.subprocess.run") as run:
            result = inspect_media(linked_media, ffprobe_bin=self.ffprobe)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_MEDIA_PATH", result["errors"][0]["code"])
        run.assert_not_called()

    def test_rejects_a_name_redirecting_media_component_before_ffprobe(self) -> None:
        from inspect_media import inspect_media

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.media,
        ), patch("inspect_media.subprocess.run") as run:
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_MEDIA_PATH", result["errors"][0]["code"])
        run.assert_not_called()

    def test_rejects_a_name_redirecting_media_ancestor_before_ffprobe(self) -> None:
        from inspect_media import inspect_media

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.root,
        ), patch("inspect_media.subprocess.run") as run:
            result = inspect_media(self.media, ffprobe_bin=self.ffprobe)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_MEDIA_PATH", result["errors"][0]["code"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
