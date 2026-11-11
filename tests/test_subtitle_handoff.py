import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("subtitle_tools", ROOT / "scripts" / "subtitle_tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)

class SubtitleSmokeTest(unittest.TestCase):
    def test_prepare_single_segment_preserves_text_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "prepared"
            result = tools.main
            import subprocess, sys
            proc = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "subtitle_tools.py"), "prepare",
                "--source-srt", str(ROOT / "tests/fixtures/source.srt"),
                "--target-srt", str(ROOT / "tests/fixtures/target.srt"),
                "--source-text", str(ROOT / "tests/fixtures/source.txt"),
                "--target-text", str(ROOT / "tests/fixtures/target.txt"),
                "--duration-seconds", "8.25", "--output-dir", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ("source-single.srt", "target-single.srt", "bilingual-single.srt"):
                cues = tools.parse_srt(out / name)
                self.assertEqual(len(cues), 1)
                self.assertEqual((cues[0].start, cues[0].end), (0, 8250))
            self.assertEqual(tools.normalized(tools.full_text(tools.parse_srt(out / "source-single.srt"))),
                             tools.normalized(Path(ROOT / "tests/fixtures/source.txt").read_text()))

    def test_unicode_target_scripts_prepare(self):
        import subprocess, sys
        targets = {
            "es": "Hoy, hagamos una pausa y escuchemos el corazón.",
            "ar": "اليوم، لنتوقف قليلًا ونصغِ إلى قلوبنا.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for code, text in targets.items():
                target_srt = base / f"{code}.srt"
                target_txt = base / f"{code}.txt"
                out = base / code
                target_srt.write_text(f"1\n00:00:00,000 --> 00:00:06,000\n{text}\n", encoding="utf-8")
                target_txt.write_text(text, encoding="utf-8")
                proc = subprocess.run([
                    sys.executable, str(ROOT / "scripts" / "subtitle_tools.py"), "prepare",
                    "--source-srt", str(ROOT / "tests/fixtures/source.srt"),
                    "--target-srt", str(target_srt),
                    "--source-text", str(ROOT / "tests/fixtures/source.txt"),
                    "--target-text", str(target_txt),
                    "--duration-seconds", "8", "--output-dir", str(out),
                ], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                cues = tools.parse_srt(out / "target-single.srt")
                self.assertEqual(len(cues), 1)
                self.assertIn(text, cues[0].text)

    def test_rejects_mismatched_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            zh = Path(tmp) / "zh.srt"
            fr = Path(tmp) / "fr.srt"
            zh.write_text("1\n00:00:00,000 --> 00:00:02,000\n你好。\n", encoding="utf-8")
            fr.write_text("1\n00:00:00,000 --> 00:00:02,001\nBonjour.\n", encoding="utf-8")
            args = type("Args", (), {"source_srt": str(zh), "target_srt": str(fr),
                "duration_seconds": "3", "source_text": str(ROOT / "tests/fixtures/source.txt"),
                "target_text": str(ROOT / "tests/fixtures/target.txt")})
            with self.assertRaisesRegex(ValueError, "timecodes differ"):
                tools.validate_pair(args)

if __name__ == "__main__":
    unittest.main()
