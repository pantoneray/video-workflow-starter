import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import post_heygen_qc as qc


class PostHeyGenQCTest(unittest.TestCase):
    def test_requires_playback_and_keeps_inputs_bound(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            video = base / "result.mp4"; video.write_bytes(b"video")
            target = base / "target.txt"; target.write_text("Hello\n", encoding="utf-8")
            srt = base / "aligned.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            profile = base / "profile.json"
            profile.write_text(json.dumps({"approved": True, "target_effective_cpm": 300,
                                           "max_cue_rate_deviation_ratio": 0.1}))
            report = base / "qc.json"
            with patch.object(qc, "inspect", return_value={"decode": "PASS", "audio": {"codec_type": "audio"}, "duration_s": 2}):
                result = qc.prepare(video, srt, target, profile, report)
            self.assertEqual(result["flagged_cues"], [])
            with self.assertRaises(ValueError): qc.verify(report)
            result["manual_review"].update(reviewer="actual reviewer", reviewed_at="2026-11-10T18:00:00+08:00",
                                            voice_match=True, lip_sync=True, audio_video_sync=True,
                                            speech_natural=True, start_end_ok=True)
            report.write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual(qc.verify(report)["status"], "human_playback_attested")
            target.write_text("Changed", encoding="utf-8")
            with self.assertRaises(ValueError): qc.verify(report)

    def test_rate_flag_requires_explanation(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            video = base / "result.mp4"; video.write_bytes(b"video")
            target = base / "target.txt"; target.write_text("Hello", encoding="utf-8")
            srt = base / "aligned.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
            profile = base / "profile.json"
            profile.write_text(json.dumps({"approved": True, "target_effective_cpm": 300,
                                           "max_cue_rate_deviation_ratio": 0.1}))
            report = base / "qc.json"
            with patch.object(qc, "inspect", return_value={"decode": "PASS", "audio": {"codec_type": "audio"}, "duration_s": 3}):
                result = qc.prepare(video, srt, target, profile, report)
            self.assertEqual(result["flagged_cues"], [1])
            result["manual_review"].update(reviewer="actual reviewer", reviewed_at="2026-11-10T18:00:00+08:00",
                                            voice_match=True, lip_sync=True, audio_video_sync=True,
                                            speech_natural=True, start_end_ok=True)
            report.write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaises(ValueError): qc.verify(report)
            result["manual_review"]["rate_exception_reason"] = "逐句试听确认自然"
            report.write_text(json.dumps(result), encoding="utf-8")
            self.assertEqual(qc.verify(report)["flagged_cues"], [1])


if __name__ == "__main__":
    unittest.main()
