import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_bundle import render
from translation_review import human_decision, sha, write_new


class BundleTests(unittest.TestCase):
    def test_pending_and_approved_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version = {"version": 1, "source": {"file": "book.md", "locator": "line 3", "original_exact": "原文"},
                       "translation": "Translation", "translation_sha256": sha("Translation"),
                       "blind_backtranslation": "回译", "independent_translation": "Independent wording",
                       "independent_review": "需复核", "glossary": []}
            write_new(root / "v1.json", version)
            pending = render([{"version": "v1.json"}], root)
            self.assertIn("待评价", pending)
            approved = human_decision(version, "实际审核人", "approve", "核对通过")
            write_new(root / "decision.json", approved)
            packet = render([{"version": "v1.json", "decision": "decision.json"}], root)
            self.assertIn("实际审核人", packet)
            self.assertIn("核对通过", packet)
            self.assertIn("Independent wording", packet)


if __name__ == "__main__":
    unittest.main()
