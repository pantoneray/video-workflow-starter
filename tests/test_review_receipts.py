import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_receipts import Receipts
import test_review_protocol


class ReceiptsTest(unittest.TestCase):
    def setUp(self):
        fixture = test_review_protocol.ReviewProtocolTest()
        fixture.setUp()
        self.current, self.receipt = fixture.round, fixture.receipt
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Receipts(self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def receive(self):
        return self.store.receive(self.current, self.receipt, entry="local_html", page="<html>Review</html>")

    def test_durable_acceptance_duplicate_archive(self):
        ident = self.receive()["id"]
        self.store.close()
        self.store = Receipts(self.root)
        self.assertEqual(self.receive()["id"], ident)
        calls = []
        def handler(receipt, routes):
            calls.append(routes["receipt_id"])
            return {"next_forms": [x["next"] for x in routes["routes"]]}
        self.assertEqual(self.store.process(ident, handler)["state"], "completed")
        self.store.process(ident, handler)
        self.assertEqual(calls, [ident])
        self.assertFalse(list((self.root / "review-signals").glob("*.json")))
        self.assertEqual(len(list((self.root / "reviews").rglob("*.html"))), 1)
        self.assertEqual(len(list((self.root / "reviews").rglob("*.json"))), 1)
        index = (self.root / "reviews/INDEX.md").read_text()
        self.store.repair_views()
        self.assertEqual((self.root / "reviews/INDEX.md").read_text(), index)

    def test_conflicting_decision_not_overwritten(self):
        self.receive()
        self.receipt["items"][0]["decision"] = "needs_changes"
        self.receipt["items"][0]["comment"] = "Fix"
        with self.assertRaises(ValueError):
            self.receive()

    def test_failure_retry_retains_signal(self):
        ident = self.receive()["id"]
        def fail(*args):
            raise RuntimeError("sensitive provider details")
        with self.assertRaises(RuntimeError):
            self.store.process(ident, fail)
        self.assertEqual(self.store.status(ident)["error"], "RuntimeError")
        self.assertTrue((self.root / "review-signals" / (ident + ".json")).exists())
        self.assertEqual(self.store.process(ident, lambda *_: {"ok": True})["state"], "completed")

    def test_unknown_processing_not_replayed(self):
        ident = self.receive()["id"]
        with self.store.db:
            self.store.db.execute("UPDATE receipts SET state='processing' WHERE id=?", (ident,))
        def forbidden(*args):
            self.fail("unknown outcome was replayed")
        self.assertEqual(self.store.process(ident, forbidden)["state"], "processing")

    def test_archive_conflict_preserved(self):
        ident = self.receive()["id"]
        row = self.store.db.execute("SELECT archive FROM receipts WHERE id=?", (ident,)).fetchone()
        path = self.root / (row["archive"] + ".html")
        path.parent.mkdir(parents=True)
        path.write_text("Do not replace")
        with self.assertRaises(ValueError):
            self.store.process(ident, lambda *_: {"ok": True})
        self.assertEqual(path.read_text(), "Do not replace")
        self.assertEqual(self.store.status(ident)["state"], "archiving")

    def test_stale_receipt_not_accepted(self):
        self.current["items"][0]["content"]["translation"] = "Changed"
        with self.assertRaises(ValueError):
            self.receive()
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
