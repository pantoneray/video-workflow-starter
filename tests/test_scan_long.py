import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scan_long import run


class LongScanTests(unittest.TestCase):
    def test_segments_resume_and_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, rules, out = root / "video.mp4", root / "rules.json", root / "result"
            source.write_bytes(b"mock video")
            rules.write_text("{}")
            calls = []

            def fake_scan(args):
                calls.append(args.scan_start)
                directory = Path(args.out)
                directory.mkdir()
                report = {"source": str(source.resolve()), "scan_start": args.scan_start,
                          "scan_seconds": args.scan_seconds,
                          "candidates": [{"id": 1, "start": args.scan_start, "end": args.scan_start+30}]}
                (directory / "candidates.json").write_text(json.dumps(report))
                return report

            first = run(source, rules, out, segment_seconds=60, scanner=fake_scan, prober=lambda _: (195, 320, 240))
            self.assertEqual(first["covered_intervals"], [[0.0, 105.0], [60.0, 165.0], [120.0, 195.0]])
            self.assertEqual(calls, [0.0, 60.0, 120.0])
            second = run(source, rules, out, segment_seconds=60, scanner=fake_scan, prober=lambda _: (195, 320, 240))
            self.assertEqual(second["segments_resumed"], 3)
            self.assertEqual(calls, [0.0, 60.0, 120.0])
            self.assertTrue(second["full_source_covered"])
            self.assertEqual(second["coverage_seconds"], 195)
            self.assertEqual([c["id"] for c in second["candidates"]], [1, 2, 3])
            with self.assertRaises(ValueError):
                run(source, rules, out, scan_start=10, scan_seconds=50, scanner=fake_scan,
                    prober=lambda _: (195, 320, 240))
            with self.assertRaises(ValueError):
                run(source, rules, out, segment_seconds=45, scanner=fake_scan,
                    prober=lambda _: (195, 320, 240))


if __name__ == "__main__":
    unittest.main()
