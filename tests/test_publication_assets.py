import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publication_assets import draft
from translation_review import human_decision, sha


class PublicationTests(unittest.TestCase):
    def test_draft_only_after_current_approval(self):
        version = {"version": 1, "source": {"original_exact": "慈悲从日常开始"},
                   "translation": "Compassion begins daily", "translation_sha256": sha("Compassion begins daily"),
                   "independent_translation": "Compassion starts each day",
                   "blind_backtranslation": "慈悲在日常开始", "independent_review": "已核对差异"}
        approval = human_decision(version, "human", "approve", "核对通过")
        result = draft(version, approval, "model-a", lambda prompt, model: {
            "title": "Daily compassion", "description": "A short reflection", "tags": ["compassion"],
            "cover_text": "Compassion"})
        self.assertEqual(result["status"], "pending_human_review")
        version["translation"] = "Changed"
        version["translation_sha256"] = sha("Changed")
        with self.assertRaises(ValueError):
            draft(version, approval, "model-a", lambda prompt, model: {})


if __name__ == "__main__":
    unittest.main()
