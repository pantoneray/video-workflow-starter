import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from caption_options import configure


class OptionsTest(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(next((ROOT / "tools/shorts-caption-templates/specs").glob("B_*.json")).read_text())

    def test_configurable_position_color_and_badge(self):
        course = {"text": "Sample lesson", "source": "test-book/chapter-1", "confirmed": True}
        result = configure(self.spec, 80, "green", course, "box")
        self.assertEqual(result["captions"]["y_center"], 1360)
        self.assertEqual(result["captions"]["highlight"], "#8BE28B")
        self.assertEqual(self.spec["captions"]["y_center"], 1440)
        module_spec = importlib.util.spec_from_file_location("renderer_test", ROOT / "tools/shorts-caption-templates/scripts/apply_template.py")
        module = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
        args = SimpleNamespace(lang="en", emph=None, overlay=None, name=None, name_sub=None, overlay_dur=3)
        ass = module.build_ass(result, [{"w": "Hello", "s": 0, "e": 1}], args, 2)
        self.assertIn(r"\pos(540,1360)", ass)
        self.assertIn(r"\an7\pos(150,250)", ass)
        self.assertIn("Sample lesson", ass)
        self.assertNotIn("course_badge", configure(self.spec))

    def test_invalid_settings_do_not_silently_clamp(self):
        for options in ({"shift_up": 500}, {"highlight": "invalid"}, {"course": {"text": "Guessed"}}):
            with self.assertRaises(ValueError):
                configure(self.spec, **options)


if __name__ == "__main__":
    unittest.main()
