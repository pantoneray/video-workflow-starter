"""Loopback review receiver. Explicit invocation; no daemon or installed timer.

The existing runner can pass a deterministic continuation callback. Never expose
this local single-user service on the LAN. Notion uses its own authenticated
adapter with the same protocol; it must not submit through this HTML endpoint.
"""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import re
from html import escape
from review_media import serve as serve_media

from review_receipts import Receipts
from review_protocol import validate_round


def make_server(root, round_path, page_path, port=0, handler=None):
    token = secrets.token_urlsafe(32)
    media_token = secrets.token_hex(24)
    round_path, page_path = Path(round_path), Path(page_path)

    def current_page():
        current = json.loads(round_path.read_text(encoding="utf-8"))
        page = page_path.read_text(encoding="utf-8")
        match = re.search(r'id="review-data" type="application/json">(.*?)</script>', page, re.S)
        if not match or json.loads(match[1]).get("content_sha256") != validate_round(current):
            raise ValueError("page no longer matches current round")
        return current, page

    class Request(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Request URLs and bodies must not enter general HTTP logs.

        def reply(self, status, body, content_type="application/json"):
            payload = (json.dumps(body, ensure_ascii=False) if content_type == "application/json" else body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

        def host_ok(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.host_ok():
                return self.reply(403, {"error": "invalid_host"})
            if self.path.startswith('/media/'):
                match = re.fullmatch(r'/media/([a-f0-9]{48})/([a-f0-9]{64})/(\d+)', self.path)
                if not match or not secrets.compare_digest(match[1], media_token):
                    return self.reply(403, {'error': 'invalid_media_handle'})
                try:
                    current, _ = current_page()
                    if match[2] != validate_round(current):
                        return self.reply(410, {'error': 'stale_media_round'})
                    return serve_media(self, current, int(match[3]), head=self.command == 'HEAD')
                except (OSError, ValueError, KeyError):
                    return self.reply(503, {'error': 'media_unavailable'})
            if self.path.startswith("/status/"):
                if not secrets.compare_digest(self.headers.get("X-Review-Token", ""), token):
                    return self.reply(403, {"error": "invalid_token"})
                ident = self.path[len("/status/"):]
                if not re.fullmatch(r"[a-f0-9]{64}", ident):
                    return self.reply(404, {"error": "unknown_receipt"})
                store = None
                try:
                    store = Receipts(root)
                    return self.reply(200, {"accepted": True, **store.status(ident)})
                except ValueError:
                    return self.reply(404, {"error": "unknown_receipt"})
                except Exception:
                    return self.reply(503, {"error": "status_unavailable"})
                finally:
                    if store is not None:
                        store.close()
            if self.path != "/review":
                return self.reply(404, {"error": "not_found"})
            try:
                current, page = current_page()
                if current['stage'] == 'T4':
                    binding = validate_round(current)
                    for n, item in enumerate(current['items']):
                        marker = f'data-local-review-video="{escape(item["id"], quote=True)}"'
                        page = page.replace(marker, marker + f' src="/media/{media_token}/{binding}/{n}"')
                config = json.dumps({"submit_url": "/submit", "status_url": "/status/", "token": token})
                page = page.replace("</head>", "<script>window.REVIEW_TRANSPORT=" + config + ";</script></head>", 1)
                self.reply(200, page, "text/html")
            except (OSError, ValueError):
                self.reply(503, {"error": "page_unavailable"})

        def do_HEAD(self):
            if not self.path.startswith('/media/'):
                return self.reply(405, {'error': 'head_only_for_media'})
            self.do_GET()

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if (not self.host_ok() or self.headers.get("Origin") != origin or
                    not secrets.compare_digest(self.headers.get("X-Review-Token", ""), token)):
                return self.reply(403, {"error": "invalid_origin_or_token"})
            if self.path != "/submit":
                return self.reply(404, {"error": "not_found"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "json_required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1048576:
                    return self.reply(413, {"error": "invalid_body_size"})
                receipt = json.loads(self.rfile.read(length))
                # Always reload the trusted current round; no client-selected file paths.
                current, page = current_page()
                store = Receipts(root)
                try:
                    result = store.receive(current, receipt, entry="local_html", page=page)
                    if handler is not None:
                        try:
                            result = store.process(result["id"], handler)
                        except Exception:
                            result = store.status(result["id"])
                    self.reply(200, {"accepted": True, **result})
                finally:
                    store.close()
            except (ValueError, TypeError, KeyError):
                self.reply(409, {"accepted": False, "error": "review_binding_or_decision_conflict"})
            except Exception:
                self.reply(503, {"accepted": False, "error": "storage_unavailable_retry_same_receipt"})

    server = HTTPServer(("127.0.0.1", port), Request)
    server.timeout = 10
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--round", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--advance-output", help="Continue locally into review artifacts after receiving")
    parser.add_argument("--metadata-model")
    parser.add_argument("--allow-metadata-model", action="store_true", help="Permit configured metadata model calls; never permits video generation")
    args = parser.parse_args()
    handler = None
    if args.advance_output:
        from review_advance import continuation
        handler = continuation(args.round, args.advance_output, model=args.metadata_model,
                               allow_model=args.allow_metadata_model)
    with make_server(args.root, args.round, args.page, args.port, handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/review", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
