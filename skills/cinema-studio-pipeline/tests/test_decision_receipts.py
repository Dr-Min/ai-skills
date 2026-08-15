import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class DecisionReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.project = base / "project"
        self.project.mkdir()
        self.store = base / "machine-state" / "decision-receipts"
        self.approval = {
            "project_id": "receipt-test",
            "approval_id": "APR_STORY_0001",
            "subject_type": "STORY",
            "subject_id": "story-contract",
            "subject_sha256": "a" * 64,
            "gate": "STORY",
            "review_status": "USER_APPROVED",
            "decided_by_type": "USER",
            "decided_by": "project-owner",
            "decided_at": "2026-08-12T01:00:00Z",
            "user_evidence_reference": "chat-receipt",
            "evidence": [
                {
                    "path": "01_story/STORY_CONTRACT.md",
                    "sha256": "a" * 64,
                    "verified_claim": "Approved story authority",
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _publish(self):
        from _cinema_common import write_json
        from decision_receipts import issue_decision_receipt

        approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            issued = issue_decision_receipt(
                self.project, "receipt-test", self.approval, approval_path
            )
            write_json(approval_path, self.approval)
        return approval_path, issued

    def test_valid_hmac_receipt_binds_exact_project_and_final_approval_bytes(self) -> None:
        from decision_receipts import verify_decision_receipt

        approval_path, issued = self._publish()
        receipt_path = Path(issued["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertIn("claims", receipt)
        self.assertIn("hmac_sha256", receipt)
        self.assertNotIn("key", receipt)

        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            error = verify_decision_receipt(
                self.project, "receipt-test", self.approval, approval_path
            )
        self.assertIsNone(error, error)

        wrong_path = approval_path.with_name("copied-approval.json")
        wrong_path.write_bytes(approval_path.read_bytes())
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            path_error = verify_decision_receipt(
                self.project, "receipt-test", self.approval, wrong_path
            )
        self.assertIsNotNone(path_error)

        copied_root = self.project.parent / "copied-project"
        copied_root.mkdir()
        copied_approval = copied_root / "09_approvals" / approval_path.name
        copied_approval.parent.mkdir(parents=True)
        copied_approval.write_bytes(approval_path.read_bytes())
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            moved_error = verify_decision_receipt(
                copied_root, "receipt-test", self.approval, copied_approval
            )
        self.assertIsNotNone(moved_error)

    def test_tampered_or_hardlinked_receipt_is_rejected(self) -> None:
        from decision_receipts import verify_decision_receipt

        approval_path, issued = self._publish()
        receipt_path = Path(issued["receipt_path"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["claims"]["gate"] = "FINISH"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            self.assertIsNotNone(
                verify_decision_receipt(
                    self.project, "receipt-test", self.approval, approval_path
                )
            )

        receipt_path.unlink()
        from decision_receipts import issue_decision_receipt
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            issued = issue_decision_receipt(
                self.project, "receipt-test", self.approval, approval_path
            )
        receipt_path = Path(issued["receipt_path"])
        alias = receipt_path.with_name("receipt-hardlink-alias.json")
        try:
            os.link(receipt_path, alias)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")
        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            self.assertIn(
                "hardlink",
                verify_decision_receipt(
                    self.project, "receipt-test", self.approval, approval_path
                ).casefold(),
            )

    def test_hardlinked_key_is_rejected(self) -> None:
        from decision_receipts import verify_decision_receipt

        approval_path, _ = self._publish()
        key_path = self.store / "hmac.key"
        alias = key_path.with_name("hmac-hardlink-alias.key")
        try:
            os.link(key_path, alias)
        except OSError as exc:
            self.skipTest(f"hard links unavailable: {exc}")

        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            error = verify_decision_receipt(
                self.project, "receipt-test", self.approval, approval_path
            )
        self.assertIsNotNone(error)
        self.assertIn("hardlink", error.casefold())

    def test_name_redirecting_store_ancestor_is_rejected(self) -> None:
        from decision_receipts import issue_decision_receipt

        outside = Path(self.temporary.name) / "outside-machine-state"
        outside.mkdir()
        redirect = Path(self.temporary.name) / "redirected-machine-state"
        try:
            redirect.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlinks unavailable: {exc}")

        approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"
        redirected_store = redirect / "decision-receipts"
        with patch(
            "decision_receipts.receipt_store_root", return_value=redirected_store
        ):
            with self.assertRaisesRegex(ValueError, "name-redirection"):
                issue_decision_receipt(
                    self.project, "receipt-test", self.approval, approval_path
                )
        self.assertEqual([], list(outside.iterdir()))

    def test_detected_name_redirecting_store_component_is_rejected_without_writes(self) -> None:
        from decision_receipts import issue_decision_receipt

        redirect = Path(self.temporary.name) / "detected-redirect"
        redirect.mkdir()
        redirected_store = redirect / "decision-receipts"
        approval_path = self.project / "09_approvals" / "APR_STORY_0001.json"
        with (
            patch("decision_receipts.receipt_store_root", return_value=redirected_store),
            patch(
                "decision_receipts._name_redirecting",
                side_effect=lambda path: Path(path) == redirect,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "name-redirection"):
                issue_decision_receipt(
                    self.project, "receipt-test", self.approval, approval_path
                )
        self.assertEqual([], list(redirect.iterdir()))

    def test_dry_run_does_not_create_machine_key_or_receipt(self) -> None:
        from decision_receipts import preview_decision_receipt

        with patch("decision_receipts.receipt_store_root", return_value=self.store):
            preview = preview_decision_receipt(
                self.project,
                "receipt-test",
                self.approval,
                self.project / "09_approvals" / "APR_STORY_0001.json",
            )

        self.assertEqual(64, len(preview["approval_sha256"]))
        self.assertFalse(self.store.exists())


if __name__ == "__main__":
    unittest.main()
