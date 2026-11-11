import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from package_video import package


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow 可选依赖未安装")
class PackagingTests(unittest.TestCase):
    def mean_volume(self, path):
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
                                "-vn", "-f", "null", "-"], capture_output=True, text=True, check=True, timeout=60)
        match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", probe.stderr)
        self.assertIsNotNone(match)
        return float(match.group(1))

    def test_burn_reviewed_srt_keeps_source(self):
        font = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
        if not font.is_file():
            self.skipTest("当前系统无测试字体")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "source.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=320x240:r=24:d=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video)], check=True, timeout=60)
            original = video.read_bytes()
            srt = root / "reviewed.srt"
            srt.write_text("1\n00:00:00,100 --> 00:00:01,900\nHello world\n\n", encoding="utf-8")
            receipt = package(video, srt, {"font_path": str(font), "width": 320, "height": 240,
                                           "font_size": 20, "safe_bottom": 24, "fps": 24}, root / "package")
            self.assertEqual(receipt["output_qc"]["decode"], "PASS")
            self.assertEqual(video.read_bytes(), original)
            self.assertTrue((root / "package" / "caption-overlays" / "cue-0001.png").is_file())
            with self.assertRaises(ValueError):
                package(video, srt, {"font_path": str(font)}, root / "package")

            intro = root / "intro.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=320x240:r=24:d=1", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-t", "1", "-c:v", "libx264", "-c:a", "aac", str(intro)], check=True, timeout=60)
            music = root / "music.wav"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=frequency=220:duration=3", str(music)], check=True, timeout=60)
            extended = package(video, srt, {"font_path": str(font), "width": 320, "height": 240,
                                             "font_size": 20, "safe_bottom": 24, "fps": 24,
                                             "intro_path": str(intro), "outro_path": str(intro),
                                             "transition_seconds": .1, "music_path": str(music)}, root / "extended")
            self.assertEqual(extended["output_qc"]["decode"], "PASS")
            self.assertTrue(3.5 < extended["output_qc"]["duration_s"] < 4.5)
            music_only = package(video, srt, {"font_path": str(font), "width": 320, "height": 240,
                                              "font_size": 20, "safe_bottom": 24, "fps": 24,
                                              "music_path": str(music), "music_volume": 0}, root / "music-only")
            mixed_level = self.mean_volume(music_only["output"])
            original_level = self.mean_volume(root / "package/final.mp4")
            self.assertLess(abs(mixed_level - original_level), 2, (mixed_level, original_level))
            self.assertIsNone(music_only["music"])


if __name__ == "__main__":
    unittest.main()
