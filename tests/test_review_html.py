import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_html import render
from review_protocol import validate_round
import test_review_protocol


class HtmlTest(unittest.TestCase):
    def test_four_templates_escape_and_source_check(self):
        f = test_review_protocol.ReviewProtocolTest()
        f.setUp()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.txt"
            source.write_text("前文\n这是原文。\n后文", encoding="utf-8")
            source_record = dict(file=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                 start=3, end=9, original_exact="这是原文。\n", locator="chapter 1")
            for item in f.round["items"]:
                item["content"].update(source=source_record, A=source_record["original_exact"],
                                       B="制作稿", title="</script><script>bad()</script>", video_url="javascript:bad()")
            for stage in ("T1", "T2", "T3", "T4"):
                f.round["stage"] = stage
                html = render(f.round)
                self.assertNotIn("<script>bad()", html)
                self.assertNotIn('href="javascript:', html)
                self.assertNotIn('value="approved" selected', html)
                self.assertNotIn('type="checkbox" checked', html)
                data = json.loads(re.search(r'id="review-data" type="application/json">(.*?)</script>', html, re.S)[1])
                self.assertEqual(data["content_sha256"], validate_round(f.round))
                self.assertEqual(len(data["items"]), 3)
            f.round["stage"] = "T1"
            source.write_text("changed")
            with self.assertRaises(ValueError):
                render(f.round)


if __name__ == "__main__":
    unittest.main()
