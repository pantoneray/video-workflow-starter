import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from translation_review import create_item, human_decision, make_version, verify_approval, model_stage


class ReviewTests(unittest.TestCase):
    def test_unknown_model_result_does_not_auto_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            attempts = []
            def fail(prompt, model):
                attempts.append(1)
                raise TimeoutError("simulated unknown")
            with self.assertRaises(TimeoutError):
                model_stage("translation", "prompt", "model-a", temp, fail)
            with self.assertRaises(RuntimeError):
                model_stage("translation", "prompt", "model-a", temp, fail)
            self.assertEqual(len(attempts), 1)
            result = model_stage("translation", "prompt", "model-a", temp,
                                 lambda prompt, model: {"items": [{"id": "1", "translation": "ok"}]},
                                 retry_unknown=True)
            self.assertEqual(result["items"][0]["translation"], "ok")
            again = model_stage("translation", "prompt", "model-a", temp, fail)
            self.assertEqual(again, result)
            self.assertEqual(len(attempts), 1)

    def test_blind_call_and_revision_invalidates_approval(self):
        prompts = []

        def provider(prompt, model):
            prompts.append((prompt, model))
            if "回译" in prompt:
                return {"items": [{"id": "1", "backtranslation": "慈悲从日常开始"}]}
            if "独立翻译" in prompt:
                return {"items": [{"id": "1", "translation": "Compassion starts in daily life"}]}
            if "独立译审" in prompt:
                return {"items": [{"id": "1", "review": "需核对术语"}]}
            return {"items": [{"id": "1", "translation": "Compassion begins in everyday life"}]}

        source = {"original_exact": "慈悲从日常开始", "file": "book.md", "locator": "line 12"}
        models = {"translation_model": "model-a", "review_model": "model-b", "backtranslation_model": "model-c"}
        v1 = create_item(source, "English", models, provider)
        self.assertEqual(len(prompts), 4)
        self.assertNotIn("Compassion begins in everyday life", prompts[1][0])
        self.assertNotIn(source["original_exact"], prompts[2][0])
        self.assertEqual(prompts[1][1], "model-b")
        self.assertEqual(prompts[2][1], "model-c")
        self.assertEqual(prompts[3][1], "model-b")
        self.assertEqual(v1["independent_translation"], "Compassion starts in daily life")
        with self.assertRaises(ValueError):
            human_decision({k: value for k, value in v1.items() if k != "independent_translation"},
                           "reviewer", "approve", "核对通过")
        self.assertEqual(v1["human_decision"], "pending")
        approval = human_decision(v1, "reviewer", "approve", "核对通过")
        self.assertEqual(approval["decision"], "approve")
        self.assertTrue(verify_approval(v1, approval)["approved"])
        altered = dict(v1, blind_backtranslation="未经审核的改动")
        with self.assertRaises(ValueError):
            verify_approval(altered, approval)
        v2 = make_version(source, "English", "Compassion starts with daily conduct", models, provider, previous=v1)
        self.assertEqual(v2["version"], 2)
        self.assertEqual(v2["human_decision"], "pending")
        self.assertNotEqual(approval["translation_sha256"], v2["translation_sha256"])
        with self.assertRaises(ValueError):
            verify_approval(v2, approval)


if __name__ == "__main__":
    unittest.main()
