import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("speech_plan", ROOT / "scripts/speech_plan.py")
speech = importlib.util.module_from_spec(spec); spec.loader.exec_module(speech)


class SpeechPlanTest(unittest.TestCase):
    def test_calibration_and_sentence_timing(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            text = base / "approved.txt"; text.write_text("Hello world.\nHow are you?\n")
            audio = base / "audio.wav"; audio.write_bytes(b"audio")
            clip = base / "clip.mp4"; clip.write_bytes(b"clip")
            with patch.object(speech, "duration", side_effect=[2.0, 2.0]):
                profile = speech.calibrate(text, audio, 2.0, "en-US", base / "profile.json")
                self.assertFalse(profile["approved"])
                with self.assertRaises(ValueError): speech.prepare(text, clip, base / "profile.json", base / "run")
                profile.update(approved=True, pause_seconds_between_cues=0.2,
                               max_duration_difference_seconds=0.3)
                (base / "profile.json").write_text(json.dumps(profile))
                result = speech.prepare(text, clip, base / "profile.json", base / "run")
            self.assertEqual(result["status"], "ready_for_review")
            self.assertEqual(result["cue_count"], 2)
            self.assertTrue((base / "run/planned-not-final.srt").is_file())
            self.assertEqual(speech.effective_count("A b! ٣"), 3)

    def test_mismatch_stops_before_subtitle(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); text = base / "approved.txt"; text.write_text("Hello world.")
            clip = base / "clip.mp4"; clip.write_bytes(b"clip")
            profile = {"approved": True, "counting_rule": "unicode_alphanumeric_excluding_spaces_and_punctuation",
                       "target_effective_cpm": 100, "pause_seconds_between_cues": 0,
                       "max_duration_difference_seconds": 0.1}
            config = base / "profile.json"; config.write_text(json.dumps(profile))
            with patch.object(speech, "duration", return_value=20.0):
                result = speech.prepare(text, clip, config, base / "run")
            self.assertEqual(result["status"], "needs_better_clip_or_text_review")
            self.assertFalse((base / "run/planned-not-final.srt").exists())


if __name__ == "__main__": unittest.main()
