import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_receiver import make_server
from review_html import render
from review_protocol import validate_round
import test_review_protocol


class ReceiverTest(unittest.TestCase):
    def test_real_http_acceptance_and_rejection(self):
        fixture = test_review_protocol.ReviewProtocolTest()
        fixture.setUp()
        fixture.round["stage"] = fixture.receipt["stage"] = "T3"
        fixture.receipt["content_sha256"] = validate_round(fixture.round)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            round_path = root / "current.json"
            round_path.write_text(json.dumps(fixture.round))
            page = root / "page.html"
            page.write_text(render(fixture.round))
            server = make_server(root / "receipts", round_path, page)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(origin + "/review", timeout=3) as response:
                    html = response.read().decode()
                token = json.loads(re.search(r"REVIEW_TRANSPORT=(.*?);</script>", html)[1])["token"]
                def submit(origin_header=origin, override=None):
                    request = urllib.request.Request(origin + "/submit", data=json.dumps(override or fixture.receipt).encode(), headers={
                        "Content-Type": "application/json", "Origin": origin_header, "X-Review-Token": token})
                    with urllib.request.urlopen(request, timeout=3) as response:
                        return json.load(response)
                first = submit()
                self.assertTrue(first["accepted"])
                self.assertEqual(first["state"], "received")
                self.assertEqual(submit()["id"], first["id"])
                status_url = origin + "/status/" + first["id"]
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(status_url, timeout=3)
                self.assertEqual(error.exception.code, 403)
                request = urllib.request.Request(status_url, headers={"X-Review-Token": token})
                with urllib.request.urlopen(request, timeout=3) as response:
                    checked = json.load(response)
                self.assertEqual(checked, first)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(origin + "/status/" + "0" * 64,
                        headers={"X-Review-Token": token}), timeout=3)
                self.assertEqual(error.exception.code, 404)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    submit("https://untrusted.example")
                self.assertEqual(error.exception.code, 403)
                fixture.round["version"] = "v2"
                round_path.write_text(json.dumps(fixture.round))
                with self.assertRaises(urllib.error.HTTPError) as error:
                    submit()
                self.assertEqual(error.exception.code, 409)
                self.assertEqual(len(list((root / "receipts/review-signals").glob("*.json"))), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
