import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_output import sha256
from prepare_upload_video import prepare
from speech_plan import prepare as speech_prepare


class UploadCopyTests(unittest.TestCase):
    def test_bounded_copy_keeps_source_and_becomes_speech_preflight_input(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, output = root / "source.mp4", root / "upload.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=24:duration=3", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000:duration=3", "-c:v", "libx264",
                            "-preset", "ultrafast", "-crf", "12", "-c:a", "aac", "-y", str(source)],
                           check=True, capture_output=True, timeout=90)
            before = sha256(source)
            result = prepare(source, output, max_bytes=350_000, max_height=360)
            self.assertLessEqual(output.stat().st_size, 350_000)
            self.assertEqual(result["status"], "local_upload_copy_ready_not_remote_accepted")
            self.assertEqual(sha256(source), before)
            self.assertEqual(json.loads(Path(str(output) + ".receipt.json").read_text())["output_sha256"], sha256(output))
            text = root / "target.txt"; text.write_text("Hello\n", encoding="utf-8")
            profile = root / "speed.json"
            profile.write_text(json.dumps({"approved": True,
                "counting_rule": "unicode_alphanumeric_excluding_spaces_and_punctuation",
                "target_effective_cpm": 100, "pause_seconds_between_cues": 0,
                "max_duration_difference_seconds": 1}))
            preflight = speech_prepare(text, output, profile, root / "preflight")
            self.assertEqual(preflight["clip_sha256"], sha256(output))
            with self.assertRaises(FileExistsError):
                prepare(source, output, max_bytes=350_000)

    def test_budget_rejects_without_touching_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "source.mp4"; source.write_bytes(b"not-video")
            before = sha256(source)
            with self.assertRaises(ValueError):
                prepare(source, root / "output.mp4", max_bytes=99_999)
            self.assertEqual(sha256(source), before)
            self.assertFalse((root / "output.mp4").exists())


if __name__ == "__main__": unittest.main()
