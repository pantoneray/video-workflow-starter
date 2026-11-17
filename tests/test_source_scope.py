import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_scope import search_sources


class ScopeTest(unittest.TestCase):
    def test_auto_missing_and_srt_provenance(self):
        themes = {"themes": [{"id": "daily", "enabled": True, "keywords": ["慈悲"]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "lesson.srt").write_text("1\n00:00:01,000 --> 00:00:05,000\n慈悲从日常开始。\n\n2\n00:00:05,000 --> 00:00:08,000\n保留后文。\n")
            config = {"paths": {"subtitle_sources": [str(root)]}}
            report = search_sources(config, themes, "daily")
            self.assertEqual(report["searched_types"], ["srt"])
            self.assertEqual(report["missing_types"], ["corpus"])
            self.assertIn("00:00:01,000", report["results"][0]["locator"])
            self.assertEqual(report["results"][0]["context_after"], "保留后文。")
            (root / "book.txt").write_text("慈悲从日常开始。")
            config["paths"]["life_corpus"] = [str(root / "book.txt")]
            report = search_sources(config, themes, "daily")
            self.assertEqual(report["searched_types"], ["corpus", "srt"])
            self.assertEqual(len(report["results"]), 1)
            self.assertEqual(len(report["duplicates"]), 1)
            selected = search_sources(config, themes, "daily", "srt")
            self.assertEqual(selected["searched_types"], ["srt"])
            self.assertIn("SRT", selected["results"][0]["locator"])


if __name__ == "__main__":
    unittest.main()
