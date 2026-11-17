import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_advance import continuation, verify_displayed_translation
from review_protocol import validate_round
from review_receipts import Receipts
from translation_review import sha, version_digest
import test_review_protocol


class AdvanceTest(unittest.TestCase):
    def test_mixed_round_generates_t3_without_waiting_for_revision(self):
        f = test_review_protocol.ReviewProtocolTest(); f.setUp()
        f.round["language"] = f.receipt["language"] = "en"
        version = {"version": 1, "source": {"original_exact": "慈悲从日常开始"}, "target_language": "en",
                   "translation": "Compassion begins daily", "translation_sha256": sha("Compassion begins daily"),
                   "independent_translation": "Compassion starts each day", "blind_backtranslation": "慈悲在日常开始", "independent_review": "核对差异"}
        item = f.round["items"][0]
        item["content"].update(translation_version=version, translation=version["translation"],
                               original=version["source"]["original_exact"],
                               backtranslation=version["blind_backtranslation"],
                               independent_translation=version["independent_translation"],
                               differences=version["independent_review"],
                               backtranslation_provider="test fixture", independent_provider="test fixture")
        self.assertIs(verify_displayed_translation(item["content"], "en"), version)
        for key in ("original", "translation", "backtranslation", "independent_translation", "differences",
                    "backtranslation_provider", "independent_provider"):
            with self.subTest(evidence=key):
                broken = dict(item["content"], **{key: ""})
                with self.assertRaises(ValueError):
                    verify_displayed_translation(broken, "en")
        f.receipt["items"][0]["content_sha256"] = version_digest(item)
        f.receipt["content_sha256"] = validate_round(f.round)
        calls = []
        def provider(prompt, model):
            calls.append(prompt)
            return dict(title="Daily compassion", description="A reflection", cover_text="Compassion", tags=["compassion"],
                        body_evidence={"title": "Compassion begins daily", "cover_text": "Compassion"})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "round.json"; current.write_text(json.dumps(f.round))
            store = Receipts(root / "store")
            try:
                received = store.receive(f.round, f.receipt, entry="local_html", page="<html>fixture</html>")
                handler = continuation(current, root / "next", model="test", provider=provider, allow_model=True)
                status = store.process(received["id"], handler)
                self.assertEqual(status["state"], "completed")
                result = json.loads(status["result"])
                self.assertEqual([i["state"] for i in result["items"]], ["next_review_ready", "awaiting_revision", "waiting"])
                self.assertTrue(Path(result["items"][0]["page"]).exists())
                store.process(received["id"], handler)
                self.assertEqual(len(calls), 1)
                self.assertFalse(list((root / "store/review-signals").glob("*.json")))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
