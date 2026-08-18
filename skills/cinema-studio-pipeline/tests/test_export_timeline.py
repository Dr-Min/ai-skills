import csv
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ExportTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.timeline = self.root / "timeline.json"
        self.output = self.root / "edit_plan.json"
        write_json(
            self.timeline,
            {
                "schema_id": "cinema-studio-pipeline/timeline@2.0.0",
                "schema_version": "2.0.0",
                "project_id": "take-me",
                "timeline_id": "main_timeline",
                "version": 2,
                "supersedes_timeline": {
                    "timeline_id": "main_timeline",
                    "version": 1,
                    "path": "07_edit/timeline.json",
                    "sha256": "c" * 64,
                    "approval_id": "APR_TIMELINE_001",
                },
                "timebase": {
                    "frame_rate_numerator": 24000,
                    "frame_rate_denominator": 1001,
                    "drop_frame": False,
                    "audio_sample_rate_hz": 48000,
                },
                "tracks": [
                    {"track_id": "TRK_MUSIC", "type": "MUSIC", "name": "Music", "order": 2, "locked": True},
                    {"track_id": "TRK_V1", "type": "VIDEO", "name": "Picture", "order": 1, "locked": True},
                ],
                "clips": [
                    {
                        "clip_id": "CLIP_B",
                        "track_id": "TRK_V1",
                        "source_type": "TAKE",
                        "source_id": "S01_SH020_T01",
                        "source_file": "b.mp4",
                        "source_sha256": "b" * 64,
                        "source_in_frame": 0,
                        "source_out_frame": 24,
                        "timeline_in_frame": 24,
                        "timeline_out_frame": 48,
                        "speed": 1,
                        "linked_event_ids": ["EVT_B"],
                        "review_status": "USER_APPROVED",
                    },
                    {
                        "clip_id": "CLIP_A",
                        "track_id": "TRK_V1",
                        "source_type": "TAKE",
                        "source_id": "S01_SH010_T01",
                        "source_file": "a.mp4",
                        "source_sha256": "a" * 64,
                        "source_in_frame": 0,
                        "source_out_frame": 24,
                        "timeline_in_frame": 0,
                        "timeline_out_frame": 24,
                        "speed": 1,
                        "linked_event_ids": ["EVT_A"],
                        "review_status": "USER_APPROVED",
                    },
                ],
                "events": [
                    {"event_id": "EVT_B", "frame": 24, "event_type": "CUT", "source": "MANUAL", "confidence": 1, "hard_lock": True, "label": "cut"},
                    {"event_id": "EVT_A", "frame": 0, "event_type": "STORY_BEAT", "source": "TIMED_STORYBOARD", "confidence": 1, "hard_lock": True, "label": "start"},
                ],
                "lock_status": "PICTURE_LOCKED",
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_exports_sorted_neutral_json_with_exact_rational_timing(self) -> None:
        from export_timeline import export_timeline

        result = export_timeline(self.timeline, self.output)
        self.assertTrue(result["ok"], result)
        plan = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual("cinema-studio-neutral-edit-plan", plan["format"])
        self.assertEqual("24000/1001", plan["timebase"]["frame_rate_rational"])
        self.assertEqual(["CLIP_A", "CLIP_B"], [clip["clip_id"] for clip in plan["clips"]])
        self.assertEqual("S01_SH010_T01", plan["clips"][0]["source_id"])
        self.assertEqual("1001/1000", plan["clips"][1]["timeline_in_time"]["seconds_rational"])
        self.assertEqual(48, plan["duration_frames"])
        self.assertIn("adapter", plan["editor_boundary"].casefold())
        self.assertNotIn("source_review_status", plan)
        self.assertNotIn("source_approval_id", plan)

    def test_is_byte_deterministic_and_refuses_implicit_overwrite(self) -> None:
        from export_timeline import export_timeline

        first = export_timeline(self.timeline, self.output)
        first_bytes = self.output.read_bytes()
        rejected = export_timeline(self.timeline, self.output)
        self.assertEqual("OUTPUT_EXISTS", rejected["errors"][0]["code"])
        forced = export_timeline(self.timeline, self.output, force=True)
        self.assertTrue(first["ok"] and forced["ok"])
        self.assertEqual(first_bytes, self.output.read_bytes())

    def test_rejects_unknown_tracks_and_non_positive_ranges(self) -> None:
        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["clips"][0]["track_id"] = "TRK_UNKNOWN"
        payload["clips"][1]["timeline_out_frame"] = 0
        write_json(self.timeline, payload)

        from export_timeline import export_timeline

        result = export_timeline(self.timeline, self.output)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("UNKNOWN_TRACK", codes)
        self.assertIn("INVALID_FRAME_RANGE", codes)

    def test_rejects_missing_duplicate_ids_and_unknown_event_links(self) -> None:
        from export_timeline import export_timeline

        cases = {
            "missing clip id": lambda payload: payload["clips"][0].update(
                {"clip_id": ""}
            ),
            "duplicate clip id": lambda payload: payload["clips"][1].update(
                {"clip_id": payload["clips"][0]["clip_id"]}
            ),
            "missing event id": lambda payload: payload["events"][0].update(
                {"event_id": ""}
            ),
            "duplicate event id": lambda payload: payload["events"][1].update(
                {"event_id": payload["events"][0]["event_id"]}
            ),
            "unknown event link": lambda payload: payload["clips"][0].update(
                {"linked_event_ids": ["EVT_UNKNOWN"]}
            ),
        }
        base_payload = json.loads(self.timeline.read_text(encoding="utf-8"))

        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name=name):
                payload = deepcopy(base_payload)
                mutate(payload)
                write_json(self.timeline, payload)
                output = self.root / f"invalid-identity-{index}.json"

                result = export_timeline(self.timeline, output)

                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    {"INVALID_CLIP", "INVALID_EVENT", "UNKNOWN_EVENT"}
                    & {item["code"] for item in result["errors"]},
                    result,
                )
                self.assertFalse(output.exists())

    def test_rejects_invalid_clip_fields_fail_closed(self) -> None:
        from export_timeline import export_timeline

        cases = {
            "clip id pattern": lambda clip: clip.update({"clip_id": "clip_a"}),
            "source type": lambda clip: clip.update({"source_type": "VIDEO"}),
            "unhashable source type": lambda clip: clip.update({"source_type": []}),
            "source id": lambda clip: clip.update({"source_id": ""}),
            "empty source file": lambda clip: clip.update({"source_file": ""}),
            "escaping source file": lambda clip: clip.update(
                {"source_file": "../outside.mp4"}
            ),
            "uppercase sha256": lambda clip: clip.update(
                {"source_sha256": "A" * 64}
            ),
            "short sha256": lambda clip: clip.update({"source_sha256": "a" * 63}),
            "boolean source frame": lambda clip: clip.update(
                {"source_in_frame": True}
            ),
            "negative source frame": lambda clip: clip.update(
                {"source_in_frame": -1}
            ),
            "boolean timeline frame": lambda clip: clip.update(
                {"timeline_out_frame": True}
            ),
            "zero speed": lambda clip: clip.update({"speed": 0}),
            "boolean speed": lambda clip: clip.update({"speed": True}),
            "infinite speed": lambda clip: clip.update({"speed": float("inf")}),
            "nan speed": lambda clip: clip.update({"speed": float("nan")}),
            "duplicate linked event": lambda clip: clip.update(
                {"linked_event_ids": ["EVT_B", "EVT_B"]}
            ),
            "invalid linked event id": lambda clip: clip.update(
                {"linked_event_ids": ["event-b"]}
            ),
            "review status": lambda clip: clip.update({"review_status": "APPROVED"}),
            "unhashable review status": lambda clip: clip.update(
                {"review_status": {}}
            ),
            "unexpected clip field": lambda clip: clip.update({"native_project": "x"}),
        }
        base_payload = json.loads(self.timeline.read_text(encoding="utf-8"))

        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name=name):
                payload = deepcopy(base_payload)
                mutate(payload["clips"][0])
                write_json(self.timeline, payload)
                output = self.root / f"invalid-clip-{index}.json"

                result = export_timeline(self.timeline, output)

                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    {"INVALID_CLIP", "INVALID_JSON"}
                    & {item["code"] for item in result["errors"]}
                )
                self.assertFalse(output.exists())

    def test_accepts_a_large_but_finite_positive_speed_without_type_coercion(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["clips"][0]["speed"] = 10**400
        write_json(self.timeline, payload)

        result = export_timeline(self.timeline, self.output)

        self.assertTrue(result["ok"], result)
        plan = json.loads(self.output.read_text(encoding="utf-8"))
        clip = next(item for item in plan["clips"] if item["clip_id"] == "CLIP_B")
        self.assertEqual(10**400, clip["speed"])

    def test_rejects_invalid_event_fields_fail_closed(self) -> None:
        from export_timeline import export_timeline

        cases = {
            "event id pattern": lambda event: event.update({"event_id": "event-a"}),
            "boolean frame": lambda event: event.update({"frame": True}),
            "negative frame": lambda event: event.update({"frame": -1}),
            "fractional frame": lambda event: event.update({"frame": 1.5}),
            "event type": lambda event: event.update({"event_type": "BEAT"}),
            "unhashable event type": lambda event: event.update({"event_type": []}),
            "source": lambda event: event.update({"source": "MODEL"}),
            "unhashable source": lambda event: event.update({"source": {}}),
            "negative confidence": lambda event: event.update({"confidence": -0.1}),
            "high confidence": lambda event: event.update({"confidence": 1.1}),
            "boolean confidence": lambda event: event.update({"confidence": True}),
            "infinite confidence": lambda event: event.update(
                {"confidence": float("inf")}
            ),
            "nan confidence": lambda event: event.update({"confidence": float("nan")}),
            "non-boolean hard lock": lambda event: event.update({"hard_lock": 1}),
            "empty label": lambda event: event.update({"label": ""}),
            "invalid time hint": lambda event: event.update(
                {"time_seconds_hint": float("nan")}
            ),
            "invalid source event id": lambda event: event.update(
                {"source_event_id": []}
            ),
            "invalid notes": lambda event: event.update({"notes": 1}),
            "unexpected event field": lambda event: event.update({"color": "red"}),
        }
        base_payload = json.loads(self.timeline.read_text(encoding="utf-8"))

        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name=name):
                payload = deepcopy(base_payload)
                mutate(payload["events"][0])
                write_json(self.timeline, payload)
                output = self.root / f"invalid-event-{index}.json"

                result = export_timeline(self.timeline, output)

                self.assertFalse(result["ok"], result)
                self.assertTrue(
                    {"INVALID_EVENT", "INVALID_JSON"}
                    & {item["code"] for item in result["errors"]}
                )
                self.assertFalse(output.exists())

    def test_rejects_invalid_top_level_fields_fail_closed(self) -> None:
        from export_timeline import export_timeline

        cases = {
            "schema id": lambda payload: payload.update({"schema_id": "timeline@2"}),
            "schema version": lambda payload: payload.update({"schema_version": "2"}),
            "project id": lambda payload: payload.update({"project_id": "Take Me"}),
            "timeline id": lambda payload: payload.update({"timeline_id": "Main-Timeline"}),
            "boolean version": lambda payload: payload.update({"version": True}),
            "missing predecessor": lambda payload: payload.update(
                {"supersedes_timeline": None}
            ),
            "predecessor path": lambda payload: payload["supersedes_timeline"].update(
                {"path": "../timeline.json"}
            ),
            "predecessor hash": lambda payload: payload["supersedes_timeline"].update(
                {"sha256": "C" * 64}
            ),
            "predecessor approval": lambda payload: payload[
                "supersedes_timeline"
            ].update({"approval_id": "approval"}),
            "missing lock status": lambda payload: payload.pop("lock_status"),
            "unhashable lock status": lambda payload: payload.update(
                {"lock_status": []}
            ),
            "locked timeline without clips": lambda payload: payload["clips"].clear(),
            "invalid notes": lambda payload: payload.update({"notes": 1}),
            "unexpected top-level field": lambda payload: payload.update(
                {"export_file": "final.mov"}
            ),
        }
        base_payload = json.loads(self.timeline.read_text(encoding="utf-8"))

        for index, (name, mutate) in enumerate(cases.items()):
            with self.subTest(name=name):
                payload = deepcopy(base_payload)
                mutate(payload)
                write_json(self.timeline, payload)
                output = self.root / f"invalid-timeline-{index}.json"

                result = export_timeline(self.timeline, output)

                self.assertFalse(result["ok"], result)
                self.assertIn(
                    "INVALID_TIMELINE", {item["code"] for item in result["errors"]}
                )
                self.assertFalse(output.exists())

    def test_rejects_invalid_timebase_and_track_fields_fail_closed(self) -> None:
        from export_timeline import export_timeline

        cases = {
            "missing timebase field": (
                "INVALID_TIMEBASE",
                lambda payload: payload["timebase"].pop("drop_frame"),
            ),
            "boolean frame rate": (
                "INVALID_TIMEBASE",
                lambda payload: payload["timebase"].update(
                    {"frame_rate_numerator": True}
                ),
            ),
            "non-boolean drop frame": (
                "INVALID_TIMEBASE",
                lambda payload: payload["timebase"].update({"drop_frame": 0}),
            ),
            "low audio sample rate": (
                "INVALID_TIMEBASE",
                lambda payload: payload["timebase"].update(
                    {"audio_sample_rate_hz": 7999}
                ),
            ),
            "unexpected timebase field": (
                "INVALID_TIMEBASE",
                lambda payload: payload["timebase"].update({"fps": 24}),
            ),
            "track id pattern": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"track_id": "music"}),
            ),
            "track type": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"type": "DATA"}),
            ),
            "unhashable track type": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"type": {}}),
            ),
            "empty track name": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"name": ""}),
            ),
            "non-boolean track lock": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"locked": 1}),
            ),
            "unexpected track field": (
                "INVALID_TRACK",
                lambda payload: payload["tracks"][0].update({"muted": False}),
            ),
        }
        base_payload = json.loads(self.timeline.read_text(encoding="utf-8"))

        for index, (name, (expected_code, mutate)) in enumerate(cases.items()):
            with self.subTest(name=name):
                payload = deepcopy(base_payload)
                mutate(payload)
                write_json(self.timeline, payload)
                output = self.root / f"invalid-container-{index}.json"

                result = export_timeline(self.timeline, output)

                self.assertFalse(result["ok"], result)
                self.assertIn(
                    expected_code, {item["code"] for item in result["errors"]}
                )
                self.assertFalse(output.exists())

    def test_rejects_non_integer_track_order_without_raising(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["tracks"][0]["order"] = {}
        write_json(self.timeline, payload)

        result = export_timeline(self.timeline, self.output)

        self.assertFalse(result["ok"], result)
        self.assertEqual("INVALID_TRACK", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.exists())

    def test_rejects_unhashable_and_duplicate_track_fields_without_raising(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["tracks"][0]["track_id"] = {"bad": "id"}
        payload["tracks"].append(
            {"track_id": "TRK_V1", "type": "VIDEO", "name": "Duplicate", "order": 1, "locked": True}
        )
        payload["clips"][0]["track_id"] = ["TRK_V1"]
        write_json(self.timeline, payload)

        result = export_timeline(self.timeline, self.output)

        self.assertFalse(result["ok"], result)
        self.assertIn("INVALID_TRACK", {item["code"] for item in result["errors"]})
        self.assertIn("INVALID_CLIP", {item["code"] for item in result["errors"]})
        self.assertFalse(self.output.exists())

    def test_rejects_duplicate_track_order_and_unbounded_timing(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["tracks"][1]["order"] = payload["tracks"][0]["order"]
        payload["timebase"]["frame_rate_numerator"] = 10 ** 400
        payload["clips"][0]["timeline_out_frame"] = 10 ** 400
        write_json(self.timeline, payload)

        result = export_timeline(self.timeline, self.output)

        self.assertFalse(result["ok"], result)
        codes = {item["code"] for item in result["errors"]}
        self.assertIn("INVALID_TRACK", codes)
        self.assertTrue({"INVALID_TIMEBASE", "INVALID_FRAME_RANGE"} & codes)
        self.assertFalse(self.output.exists())

    def test_rejects_legacy_delivery_status_and_export_fields(self) -> None:
        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["lock_status"] = "DELIVERY_APPROVED"
        payload["export_file"] = "08_delivery/masters/final.mov"
        write_json(self.timeline, payload)

        from export_timeline import export_timeline

        result = export_timeline(self.timeline, self.output)
        self.assertIn("INVALID_LOCK_STATUS", {item["code"] for item in result["errors"]})

    def test_csv_export_has_one_non_force_winner_under_concurrency(self) -> None:
        from export_timeline import export_timeline

        output = self.root / "edit_plan.csv"
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: export_timeline(self.timeline, output, output_format="csv"),
                    range(12),
                )
            )
        self.assertEqual(1, sum(result["ok"] for result in results), results)
        self.assertTrue(output.read_text(encoding="utf-8-sig").startswith("row_type,"))
        self.assertEqual([], list(self.root.glob(".edit_plan.csv.*.tmp")))

    def test_csv_losslessly_serializes_sorted_clips_and_events(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["clips"][0]["source_id"] = "source,with,commas"
        payload["events"][0].update(
            {
                "time_seconds_hint": 1.001,
                "source_event_id": None,
                "notes": "optional event notes",
            }
        )
        write_json(self.timeline, payload)
        csv_output = self.root / "edit_plan.csv"
        json_output = self.root / "edit_plan.json"

        csv_result = export_timeline(self.timeline, csv_output, output_format="csv")
        json_result = export_timeline(self.timeline, json_output, output_format="json")

        self.assertTrue(csv_result["ok"], csv_result)
        self.assertTrue(json_result["ok"], json_result)
        self.assertEqual(2, csv_result["clips"])
        self.assertEqual(2, csv_result["events"])
        plan = json.loads(json_output.read_text(encoding="utf-8"))
        with csv_output.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(["CLIP", "CLIP", "EVENT", "EVENT"], [row["row_type"] for row in rows])
        self.assertEqual(
            ["CLIP_A", "CLIP_B"],
            [row["clip_id"] for row in rows if row["row_type"] == "CLIP"],
        )
        self.assertEqual(
            ["EVT_A", "EVT_B"],
            [row["event_id"] for row in rows if row["row_type"] == "EVENT"],
        )
        self.assertEqual(
            plan["clips"],
            [json.loads(row["record_json"]) for row in rows if row["row_type"] == "CLIP"],
        )
        self.assertEqual(
            plan["events"],
            [json.loads(row["record_json"]) for row in rows if row["row_type"] == "EVENT"],
        )

    def test_rejects_output_aliasing_source_and_malformed_members(self) -> None:
        from export_timeline import export_timeline

        alias = export_timeline(self.timeline, self.timeline, force=True)
        self.assertIn("OUTPUT_ALIASES_INPUT", {item["code"] for item in alias["errors"]})
        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["tracks"] = [1]
        write_json(self.timeline, payload)
        malformed = export_timeline(self.timeline, self.output)
        self.assertIn("INVALID_TRACK", {item["code"] for item in malformed["errors"]})

    def test_rejects_a_hardlinked_output_alias_even_with_force(self) -> None:
        from export_timeline import export_timeline

        os.link(self.timeline, self.output)
        before = self.timeline.read_bytes()

        result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_INPUT", result["errors"][0]["code"])
        self.assertEqual(before, self.timeline.read_bytes())

    def test_json_rechecks_for_a_hardlink_alias_after_staging_before_force_publish(self) -> None:
        from _cinema_common import json_bytes as serialize_json
        from export_timeline import export_timeline

        before = self.timeline.read_bytes()

        def serialize_then_plant_alias(payload):
            serialized = serialize_json(payload)
            os.link(self.timeline, self.output)
            return serialized

        with patch(
            "export_timeline.json_bytes",
            side_effect=serialize_then_plant_alias,
            create=True,
        ):
            result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("OUTPUT_ALIASES_INPUT", result["errors"][0]["code"])
        self.assertEqual(before, self.timeline.read_bytes())
        self.assertTrue(os.path.samefile(self.timeline, self.output))

    def test_rejects_a_staged_temporary_that_aliases_the_source_timeline(self) -> None:
        from export_timeline import _stage_json as real_stage_json
        from export_timeline import export_timeline

        before = self.timeline.read_bytes()

        def stage_then_replace_with_source_alias(output, plan):
            temporary = real_stage_json(output, plan)
            temporary.unlink()
            os.link(self.timeline, temporary)
            return temporary

        with patch(
            "export_timeline._stage_json", side_effect=stage_then_replace_with_source_alias
        ):
            result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertIn(
            result["errors"][0]["code"],
            {"OUTPUT_ALIASES_INPUT", "UNSAFE_OUTPUT_PATH"},
        )
        self.assertEqual(before, self.timeline.read_bytes())
        self.assertFalse(self.output.exists())

    def test_json_rechecks_the_output_path_after_staging_before_force_publish(self) -> None:
        from _cinema_common import json_bytes as serialize_json
        from export_timeline import export_timeline

        redirect_active = False

        def serialize_then_redirect(payload):
            nonlocal redirect_active
            serialized = serialize_json(payload)
            redirect_active = True
            return serialized

        def is_redirecting(path) -> bool:
            return redirect_active and Path(path) == self.output

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=is_redirecting,
        ), patch(
            "export_timeline.json_bytes",
            side_effect=serialize_then_redirect,
        ):
            result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_OUTPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        self.assertEqual([], list(self.root.glob(".edit_plan.json.*.tmp")))

    def test_rejects_a_name_redirecting_timeline_before_reading_it(self) -> None:
        from export_timeline import export_timeline

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.timeline,
        ), patch("export_timeline.read_json") as read:
            result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_TIMELINE_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        read.assert_not_called()

    def test_rejects_a_name_redirecting_output_before_reading_the_timeline(self) -> None:
        from export_timeline import export_timeline

        with patch(
            "_cinema_common.is_name_redirecting_reparse",
            side_effect=lambda path: Path(path) == self.output,
        ), patch("export_timeline.read_json") as read:
            result = export_timeline(self.timeline, self.output, force=True)

        self.assertFalse(result["ok"], result)
        self.assertEqual("UNSAFE_OUTPUT_PATH", result["errors"][0]["code"])
        self.assertFalse(self.output.exists())
        read.assert_not_called()

    def test_csv_neutralizes_formula_cells_without_changing_json_values(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        malicious_clip = payload["clips"][0]
        malicious_event = payload["events"][0]
        malicious_clip["source_id"] = "\u200b@SUM(1,1)"
        malicious_clip["source_file"] = " \t=HYPERLINK(\"https://example.invalid\")"
        malicious_event["label"] = "\r\n-CMD()"
        malicious_event["notes"] = "\x00+cmd|' /C calc'!A0"
        write_json(self.timeline, payload)
        csv_output = self.root / "edit_plan.csv"
        json_output = self.root / "edit_plan-safe.json"

        csv_result = export_timeline(self.timeline, csv_output, output_format="csv")
        json_result = export_timeline(self.timeline, json_output, output_format="json")

        self.assertTrue(csv_result["ok"], csv_result)
        self.assertTrue(json_result["ok"], json_result)
        with csv_output.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        clip_row = next(item for item in rows if item["clip_id"] == "CLIP_B")
        event_row = next(item for item in rows if item["event_id"] == "EVT_B")
        self.assertEqual("'\u200b@SUM(1,1)", clip_row["source_id"])
        self.assertEqual(
            "' \t=HYPERLINK(\"https://example.invalid\")",
            clip_row["source_file"],
        )
        self.assertEqual("'\r\n-CMD()", event_row["label"])
        self.assertEqual("'\x00+cmd|' /C calc'!A0", event_row["notes"])
        json_plan = json.loads(json_output.read_text(encoding="utf-8"))
        json_clip = next(item for item in json_plan["clips"] if item["clip_id"] == "CLIP_B")
        json_event = next(item for item in json_plan["events"] if item["event_id"] == "EVT_B")
        self.assertEqual(malicious_clip["source_id"], json_clip["source_id"])
        self.assertEqual(malicious_clip["source_file"], json_clip["source_file"])
        self.assertEqual(malicious_event["label"], json_event["label"])
        self.assertEqual(malicious_event["notes"], json_event["notes"])

    def test_schema_valid_unencodable_text_fails_closed_for_every_format(self) -> None:
        from export_timeline import export_timeline

        payload = json.loads(self.timeline.read_text(encoding="utf-8"))
        payload["events"][0]["label"] = "\ud800"
        write_json(self.timeline, payload)

        for output_format in ("json", "csv"):
            with self.subTest(output_format=output_format):
                output = self.root / f"unencodable.{output_format}"

                result = export_timeline(
                    self.timeline, output, output_format=output_format
                )

                self.assertFalse(result["ok"], result)
                self.assertEqual("OUTPUT_WRITE_FAILED", result["errors"][0]["code"])
                self.assertFalse(output.exists())
                self.assertEqual(
                    [], list(self.root.glob(f".{output.name}.*.tmp"))
                )


if __name__ == "__main__":
    unittest.main()
