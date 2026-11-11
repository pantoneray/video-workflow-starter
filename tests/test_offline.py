import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OfflineSample(unittest.TestCase):
    def test_slice_qc_preserve_source_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "color=c=blue:s=320x240:r=24:d=3", "-f", "lavfi",
                "-i", "sine=frequency=440:duration=3", "-c:v", "libx264",
                "-c:a", "aac", "-shortest", str(source),
            ], check=True, timeout=60)
            before = (source.stat().st_size, source.stat().st_mtime_ns,
                      hashlib.sha256(source.read_bytes()).hexdigest())
            cuts = base / "cuts.json"
            cuts.write_text('[{"start":0.5,"end":2.5,"label":"sample"}]')
            output = base / "run-001"
            cmd = [sys.executable, str(ROOT / "scripts/slice.py"), "--input", str(source),
                   "--cuts", str(cuts), "--out", str(output)]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            manifest = json.loads((output / "manifest.json").read_text())
            clip = Path(manifest["segments"][0]["file"])
            self.assertTrue(clip.is_file())
            self.assertEqual(manifest["segments"][0]["sha256"], hashlib.sha256(clip.read_bytes()).hexdigest())
            qc = subprocess.run([sys.executable, str(ROOT / "scripts/check_output.py"),
                                 "--input", str(clip), "--out", str(output / "qc.json")],
                                check=True, capture_output=True, text=True, timeout=120)
            report = json.loads(qc.stdout)
            self.assertEqual(report["decode"], "PASS")
            self.assertTrue(1.8 <= report["duration_s"] <= 2.2)
            self.assertIsNotNone(report["video"])
            self.assertIsNotNone(report["audio"])
            self.assertEqual(before, (source.stat().st_size, source.stat().st_mtime_ns,
                                      hashlib.sha256(source.read_bytes()).hexdigest()))
            rerun = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(rerun.returncode, 0)


if __name__ == "__main__":
    unittest.main()
