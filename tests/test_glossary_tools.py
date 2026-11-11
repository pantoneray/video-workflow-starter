import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from glossary_tools import select
from translation_review import human_decision, make_version, model_config_for_source, verify_approval


class GlossaryTests(unittest.TestCase):
    def test_only_matching_language_and_source_terms_are_selected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            csv_file = root / "terms.csv"
            csv_file.write_text("source,target,language\n慈悲,compassion,English\n戒律,discipline,English\n慈悲,compasión,Spanish\n", encoding="utf-8")
            config = {"paths": {"glossary": [str(csv_file)]}}
            terms = select(config, "慈悲从日常开始", "English")
            self.assertEqual([(x["source"], x["target"]) for x in terms], [("慈悲", "compassion")])
            self.assertEqual(terms[0]["status"], "provided_for_human_review")
            self.assertEqual(len(terms[0]["source_sha256"]), 64)

    def test_markdown_text_json_and_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".DS_Store").write_text("ignored")
            (root / "one.md").write_text("# 术语\n| source | target | language |\n| --- | --- | --- |\n| 因缘 | dependent arising | English |\n")
            (root / "two.txt").write_text("慈悲 = compassion\n")
            (root / "three.json").write_text(json.dumps({"terms": [{"source": "修行", "target": "practice", "language": "English"}]}))
            config = {"paths": {"glossary": str(root)}}
            terms = select(config, "因缘与慈悲也是修行", "English")
            self.assertEqual({x["source"] for x in terms}, {"因缘", "慈悲", "修行"})
            (root / "conflict.csv").write_text("source,target,language\n慈悲,kindness,English\n")
            with self.assertRaises(ValueError):
                select(config, "慈悲", "English")

    def test_revisions_reselect_current_terms_and_invalidate_old_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            terms = root / "terms.csv"
            terms.write_text("source,target,language\n慈悲,compassion,English\n")
            project = root / "config.json"
            project.write_text(json.dumps({"paths": {"glossary": "terms.csv"}}))
            source = {"original_exact": "慈悲从日常开始", "file": "book.md", "locator": "line 1"}
            base = {"translation_model": "a", "review_model": "b", "backtranslation_model": "c", "glossary": []}
            first = model_config_for_source(base, source, "English", project)
            with self.assertRaises(ValueError):
                model_config_for_source({**base, "glossary": [{"source": "慈悲", "target": "kindness"}]},
                                        source, "English", project)
            calls = []
            def stage_call(stage, prompt, model):
                calls.append((stage, prompt))
                field = {"independent_translation": "translation", "backtranslation": "backtranslation",
                         "independent_review": "review"}[stage]
                return {"items": [{"id": "1", field: "checked"}]}
            v1 = make_version(source, "English", "Compassion starts daily", first, stage_call=stage_call)
            self.assertIn("compassion", calls[0][1])
            self.assertNotIn(str(terms), calls[0][1])
            self.assertNotIn(first["glossary"][0]["source_sha256"], calls[0][1])
            self.assertNotIn("术语参考", calls[1][1])
            self.assertNotIn(source["original_exact"], calls[1][1])
            approval = human_decision(v1, "reviewer", "approve", "checked")
            with self.assertRaises(ValueError):
                model_config_for_source(base, source, "English", previous=v1)
            terms.write_text("source,target,language\n慈悲,loving kindness,English\n")
            second = model_config_for_source(base, source, "English", project, v1)
            v2 = make_version(source, "English", "Compassion starts daily", second,
                              previous=v1, stage_call=stage_call)
            self.assertNotEqual(v1["glossary"], v2["glossary"])
            with self.assertRaises(ValueError):
                verify_approval(v2, approval)


if __name__ == "__main__": unittest.main()
