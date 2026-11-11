import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import guide
from delivery import init


class GuideTests(unittest.TestCase):
    def fake_environment(self, command, **kwargs):
        class Result:
            returncode = 0
            stdout = "PASS\nPython 3.12"
        return Result()

    def test_read_only_plan_and_parallel_stages(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            corpus = root / "corpus.md"; corpus.write_text("sample")
            glossary = root / "glossary.csv"; glossary.write_text("term")
            video = root / "video.mp4"; video.write_bytes(b"sample")
            output = root / "output"; output.mkdir()
            config = root / "video-config.json"
            config.write_text(json.dumps({"paths": {"life_corpus": [corpus.name],
                                                    "deep_corpus": [corpus.name],
                                                    "glossary": [glossary.name],
                                                    "video_sources": [video.name],
                                                    "output": output.name}}))
            before = config.read_bytes()
            planned = guide.plan(config, environment_runner=self.fake_environment)
            self.assertEqual([x["stage"] for x in planned["stages"]], ["source", "clips"])
            self.assertFalse(planned["external_or_paid_action_taken"])
            self.assertEqual(config.read_bytes(), before)
            run = root / "task"; init(run, "task")
            after = guide.plan(config, run, environment_runner=self.fake_environment)
            self.assertEqual([x["stage"] for x in after["stages"]], ["source", "clips"])
            self.assertFalse(after["delivery"]["artifact_inventory_complete"])
            self.assertEqual(guide.next_stages(["translation", "youtube"]), ["translation"])
            self.assertEqual(guide.next_stages(["youtube"]), ["youtube"])

    def test_stage_specific_dependencies_and_oauth_override_warning(self):
        seen = []
        def runner(command, **kwargs):
            seen.append(command)
            return self.fake_environment(command, **kwargs)
        with patch.dict(guide.os.environ, {"HEYGEN_API_KEY": "dummy"}):
            result = guide.plan(stage="heygen", environment_runner=runner)
        self.assertTrue(result["stages"][0]["heygen_api_key_overrides_oauth"])
        self.assertIn("--with-heygen", seen[0])
        self.assertFalse(result["external_or_paid_action_taken"])


if __name__ == "__main__": unittest.main()
