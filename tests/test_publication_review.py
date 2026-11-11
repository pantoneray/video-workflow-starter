import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publication_review import decide, verify
from check_output import sha256
from translation_review import human_decision, sha, version_digest, write_new


@unittest.skipUnless(importlib.util.find_spec("PIL"), "发布封面审核需要可选 Pillow 依赖")
class PublicationReviewTests(unittest.TestCase):
    def test_approval_binds_current_text_metadata_and_actual_cover(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            version = {"version": 1, "source": {"original_exact": "慈悲从日常开始"},
                       "translation": "Compassion begins daily", "translation_sha256": sha("Compassion begins daily"),
                       "independent_translation": "Compassion starts each day",
                       "blind_backtranslation": "慈悲在日常开始", "independent_review": "已核对差异"}
            approval = human_decision(version, "text reviewer", "approve", "核对通过")
            candidate = {"status": "pending_human_review", "version": 1,
                         "version_sha256": version_digest(version), "translation_sha256": version["translation_sha256"],
                         "title": "Daily compassion", "description": "A reflection", "tags": ["compassion"],
                         "cover_text": "Compassion"}
            for name, data in (("version.json", version), ("approval.json", approval), ("candidate.json", candidate)):
                write_new(root / name, data)
            from PIL import Image
            cover = root / "cover.png"
            Image.new("RGB", (320, 320), "blue").save(cover)
            video = root / "final.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=320x320:r=24:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video)], check=True, timeout=60)
            with self.assertRaises(ValueError):
                decide(root / "candidate.json", root / "version.json", root / "approval.json", video, None,
                       "publication reviewer", "approve", "checked", root / "missing-cover.json")
            decide(root / "candidate.json", root / "version.json", root / "approval.json", video, cover,
                   "publication reviewer", "approve", "checked video, cover and metadata", root / "decision.json")
            result = verify(root / "candidate.json", root / "decision.json", root / "version.json", root / "approval.json")
            self.assertEqual(result["title"], "Daily compassion")
            self.assertEqual(result["cover_sha256"], sha256(cover))
            self.assertEqual(result["video_sha256"], sha256(video))
            other = root / "other.mp4"; other.write_bytes(b"different")
            with self.assertRaises(ValueError):
                verify(root / "candidate.json", root / "decision.json", root / "version.json", root / "approval.json", video_path=other)
            changed = dict(candidate, title="Different")
            write_new(root / "changed.json", changed)
            with self.assertRaises(ValueError):
                verify(root / "changed.json", root / "decision.json", root / "version.json", root / "approval.json")
            cover.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify(root / "candidate.json", root / "decision.json", root / "version.json", root / "approval.json")


if __name__ == "__main__":
    unittest.main()
