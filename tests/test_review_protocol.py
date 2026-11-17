import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_protocol import validate_receipt, validate_round
from translation_review import version_digest


class ReviewProtocolTest(unittest.TestCase):
    def setUp(self):
        self.round = dict(schema_version=1, round_id="sample-T2-v1", task_id="sample", stage="T2",
                          language="id", version="v1", batch="sample", entry="local_html",
                          items=[dict(id=str(i), version="r1", content={"translation": "Sample " + str(i)},
                                      required_checks=["meaning", "identity"], approval_blockers=[]) for i in range(3)])
        self.receipt = {k: self.round[k] for k in ("schema_version", "round_id", "task_id", "stage", "language", "version", "entry")}
        self.receipt.update(content_sha256=validate_round(self.round), submitted_at="2026-11-17T10:00:00Z", items=[
            dict(id=i["id"], version=i["version"], content_sha256=version_digest(i), decision=d,
                 comment="Change wording" if d == "needs_changes" else "", checks={"meaning": True, "identity": True})
            for i, d in zip(self.round["items"], ("approved", "needs_changes", "pending"))])

    def validate(self):
        return validate_receipt(self.round, self.receipt, entry="local_html")

    def test_mixed_routes(self):
        result = self.validate()
        self.assertEqual([x["next"] for x in result["routes"]], ["T3", "revision", "waiting"])
        self.assertFalse(result["external_actions_authorized"])

    def test_repeat_click_identity(self):
        before = self.validate()["receipt_id"]
        self.receipt["submitted_at"] = "2026-11-17T11:00:00Z"
        self.receipt["items"].reverse()
        self.assertEqual(before, self.validate()["receipt_id"])

    def test_stale_changes(self):
        for key in ("version", "language", "round_id", "content_sha256", "entry"):
            with self.subTest(key=key):
                r = copy.deepcopy(self.receipt)
                r[key] = "wrong"
                with self.assertRaises(ValueError):
                    validate_receipt(self.round, r, entry="local_html")

    def test_no_default_approval_or_checks(self):
        for change in ({"decision": None}, {"checks": {}}, {"checks": {"meaning": 1, "identity": True}}):
            with self.subTest(change=change):
                r = copy.deepcopy(self.receipt)
                r["items"][0].update(change)
                with self.assertRaises(ValueError):
                    validate_receipt(self.round, r, entry="local_html")

    def test_missing_gemini_blocks_approval(self):
        self.round["items"][0]["approval_blockers"] = ["gemini_review_missing"]
        self.receipt["content_sha256"] = validate_round(self.round)
        self.receipt["items"][0]["content_sha256"] = version_digest(self.round["items"][0])
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_item(self):
        self.receipt["items"][1] = copy.deepcopy(self.receipt["items"][0])
        with self.assertRaises(ValueError):
            self.validate()

    def test_changes_require_comment(self):
        self.receipt["items"][1]["comment"] = "  "
        with self.assertRaises(ValueError):
            self.validate()

    def test_t1_selection_and_t3_t4_no_generation(self):
        for stage, target in (("T1", "T2"), ("T3", "await_media_review"), ("T4", "await_upload_authorization")):
            self.round["stage"] = self.receipt["stage"] = stage
            self.round["items"][0]["content"]["A"] = "Source"
            self.receipt["content_sha256"] = validate_round(self.round)
            self.receipt["items"][0]["content_sha256"] = version_digest(self.round["items"][0])
            if stage == "T1":
                with self.assertRaises(ValueError):
                    self.validate()
                self.receipt["items"][0]["selected_text"] = "A"
            self.assertEqual(self.validate()["routes"][0]["next"], target)


if __name__ == "__main__":
    unittest.main()
