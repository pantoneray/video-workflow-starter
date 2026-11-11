import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


heygen = load("heygen_portable")
youtube = load("youtube_portable")
from translation_review import human_decision, sha, write_new


class FakeResponse:
    status_code = 200
    def __init__(self, data=None, content=b"video-bytes"):
        self.data = data or {}; self.content = content
    def raise_for_status(self): pass
    def json(self): return self.data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield self.content


class IntegrationTests(unittest.TestCase):
    def test_youtube_client_path_is_relative_to_config(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            config = base / "youtube.json"
            config.write_text(json.dumps({"channel_id": "channel-1", "expected_email": "owner@example.test",
                "gcp_project_id": "project-1", "client_secret_path": "credentials/client.json"}))
            argv = ["youtube_portable.py", "verify", "--config", str(config)]
            with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, "argv", argv), \
                    patch.object(youtube, "credentials", return_value=object()) as credentials, \
                    patch.object(youtube, "verify_identity", return_value={"account_verified": True}):
                self.assertEqual(youtube.main(), 0)
            self.assertEqual(Path(credentials.call_args.args[1]), (base / "credentials/client.json").resolve())

    def test_youtube_rejects_unapproved_metadata_before_oauth(self):
        import publication_review
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "youtube.json"
            config.write_text(json.dumps({"channel_id": "channel-1", "expected_email": "owner@example.test",
                                          "gcp_project_id": "project-1", "client_secret_path": "unused.json"}))
            argv = ["youtube_portable.py", "upload-private", "--config", str(config), "--file", "unused.mp4",
                    "--candidate", "unused-candidate.json", "--publication-decision", "unused-decision.json",
                    "--version", "unused-version.json", "--approval", "unused-approval.json", "--out", "unused-out"]
            with contextlib.redirect_stderr(io.StringIO()), patch.object(sys, "argv", argv), \
                 patch.object(publication_review, "verify", side_effect=ValueError("unapproved")), \
                 patch.object(youtube, "credentials") as credentials:
                self.assertEqual(youtube.main(), 2)
                credentials.assert_not_called()

    def test_youtube_cli_uses_approved_publication_values(self):
        import publication_review
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "youtube.json"
            config.write_text(json.dumps({"channel_id": "channel-1", "expected_email": "owner@example.test",
                                          "gcp_project_id": "project-1", "client_secret_path": "unused.json"}))
            out = Path(d) / "receipt"
            argv = ["youtube_portable.py", "upload-private", "--config", str(config), "--file", "final.mp4",
                    "--candidate", "candidate.json", "--publication-decision", "decision.json",
                    "--version", "version.json", "--approval", "approval.json", "--out", str(out)]
            approved = {"title": "Approved title", "description": "Approved description", "tags": ["approved"],
                        "candidate_sha256": "candidate-hash"}
            identity = {"google_account_email": "owner@example.test", "gcp_project_id": "project-1"}
            def fake_upload(*args):
                out.mkdir()
                return {"video_id": "video-1", "privacyStatus": "private"}
            with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, "argv", argv), \
                 patch.object(publication_review, "verify", return_value=approved), \
                 patch.object(youtube, "credentials", return_value=object()), \
                 patch.object(youtube, "verify_identity", return_value=identity), \
                 patch.object(youtube, "upload", side_effect=fake_upload) as upload:
                self.assertEqual(youtube.main(), 0)
                self.assertEqual(upload.call_args.args[3:5], ("Approved title", "Approved description"))
                self.assertEqual(upload.call_args.args[-1], ["approved"])
            saved = json.loads((out / "upload-verified.json").read_text())
            self.assertEqual(saved["video_id"], "video-1")
            self.assertEqual(saved["publication_candidate_sha256"], "candidate-hash")

    def test_youtube_processing_result_saved_for_resume(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            config = base / "youtube.json"
            config.write_text(json.dumps({"channel_id": "channel-1", "expected_email": "owner@example.test",
                                          "gcp_project_id": "project-1", "client_secret_path": "unused.json"}))
            output = base / "processing.json"
            argv = ["youtube_portable.py", "wait-processing", "--config", str(config),
                    "--video-id", "video-1", "--out", str(output)]
            identity = {"google_account_email": "owner@example.test", "gcp_project_id": "project-1"}
            status = {"video_id": "video-1", "channel_id": "channel-1",
                      "privacyStatus": "private", "processingStatus": "succeeded"}
            with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, "argv", argv), \
                 patch.object(youtube, "credentials", return_value=object()), \
                 patch.object(youtube, "verify_identity", return_value=identity), \
                 patch.object(youtube, "wait_processing", return_value=status) as waiting:
                self.assertEqual(youtube.main(), 0)
                self.assertEqual(json.loads(output.read_text())["processingStatus"], "succeeded")
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(youtube.main(), 2)
                self.assertEqual(waiting.call_count, 1)

    def test_youtube_thumbnail_requires_this_private_upload_before_oauth(self):
        import publication_review
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config = root / "youtube.json"
            config.write_text(json.dumps({"channel_id": "channel-1", "expected_email": "owner@example.test",
                                          "gcp_project_id": "project-1", "client_secret_path": "unused.json"}))
            receipt = root / "upload-verified.json"
            approved = {"candidate_sha256": "candidate-1", "video_sha256": "video-hash"}
            valid = {"video_id": "video-1", "channel_id": "channel-1", "privacyStatus": "private",
                     "publication_candidate_sha256": "candidate-1", "sha256": "video-hash",
                     "google_account_email": "owner@example.test", "gcp_project_id": "project-1"}
            receipt.write_text(json.dumps({**valid, "video_id": "another-video"}))
            argv = ["youtube_portable.py", "set-thumbnail", "--config", str(config),
                    "--video-id", "video-1", "--image", "approved.png", "--receipt", str(root / "thumbnail.json"),
                    "--upload-receipt", str(receipt), "--candidate", "candidate.json",
                    "--publication-decision", "decision.json", "--version", "v1.json", "--approval", "approval.json"]
            with contextlib.redirect_stderr(io.StringIO()), patch.object(sys, "argv", argv), \
                 patch.object(publication_review, "verify", return_value=approved), \
                 patch.object(youtube, "credentials") as credentials:
                self.assertEqual(youtube.main(), 2)
                credentials.assert_not_called()
            receipt.write_text(json.dumps(valid))
            self.assertEqual(youtube.verify_thumbnail_upload(receipt, approved, "video-1", "channel-1",
                                                             "owner@example.test", "project-1"), youtube.sha256(receipt))
            for altered in ({"sha256": "other-video"}, {"publication_candidate_sha256": "other-candidate"},
                            {"google_account_email": "other@example.test"}, {"privacyStatus": "public"}):
                receipt.write_text(json.dumps({**valid, **altered}))
                with self.assertRaises(ValueError):
                    youtube.verify_thumbnail_upload(receipt, approved, "video-1", "channel-1",
                                                    "owner@example.test", "project-1")

    def test_api_key_account_mismatch_blocks_paid_cli_before_submission(self):
        argv = ["heygen_portable.py", "create-proofread", "--payload", "unused.json",
                "--receipt", "unused-receipt.json", "--preflight", "unused-preflight.json",
                "--asset-receipt", "unused-asset.json", "--text", "unused.txt",
                "--review-version", "unused-version.json", "--review-decision", "unused-decision.json",
                "--expected-email", "owner@example.test", "--paid-authorization", "unused-paid.json", "--confirm-paid"]
        with contextlib.redirect_stderr(io.StringIO()) as error, patch.object(sys, "argv", argv), patch.dict(heygen.os.environ, {"HEYGEN_API_KEY": "fake-key"}), \
             patch.object(heygen, "auth_check", side_effect=ValueError("wrong account")), \
             patch.object(heygen, "create_proofread") as create:
            self.assertEqual(heygen.main(), 2)
            create.assert_not_called()
        self.assertIn("wrong account", error.getvalue())

    def test_youtube_read_retry_is_bounded(self):
        class Read:
            calls = 0
            def execute(self):
                self.calls += 1
                if self.calls < 3: raise OSError("temporary network failure")
                return {"ok": True}
        request = Read()
        with patch.object(youtube.time, "sleep") as sleep:
            self.assertTrue(youtube.read_request(request)["ok"])
        self.assertEqual(request.calls, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_heygen_upload_submit_status_download(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "source.mp4"; source.write_bytes(b"source-bytes")
            preflight = base / "preflight.json"
            text_path = base / "target.txt"; text_path.write_text("Hello\n", encoding="utf-8")
            preflight.write_text(json.dumps({"status": "ready_for_review",
                "purpose": "estimated_pre_heygen_timeline_not_final_audio_alignment",
                "clip_sha256": heygen.digest(source), "text_sha256": heygen.digest(text_path)}))
            version = {"version": 1, "source": {"file": "sample.md", "locator": "line 1", "original_exact": "你好"},
                       "target_language": "English", "translation": "Hello", "translation_sha256": sha("Hello"),
                       "independent_translation": "Hello", "blind_backtranslation": "你好", "independent_review": "已核"}
            write_new(base / "v1.json", version)
            write_new(base / "decision.json", human_decision(version, "human", "approve", "核对通过"))
            fake_requests = types.SimpleNamespace(
                post=lambda *args, **kwargs: FakeResponse({"data": {"asset_id": "asset-1"}}),
                get=lambda *args, **kwargs: FakeResponse(content=b"downloaded-video"),
            )
            fake_encoder = types.ModuleType("requests_toolbelt.multipart.encoder")
            class Encoder:
                content_type = "multipart/form-data; boundary=test"
                def __init__(self, fields): self.fields = fields
            fake_encoder.MultipartEncoder = Encoder
            fake_multipart = types.ModuleType("requests_toolbelt.multipart"); fake_multipart.encoder = fake_encoder
            fake_toolbelt = types.ModuleType("requests_toolbelt"); fake_toolbelt.multipart = fake_multipart
            with patch.dict(sys.modules, {"requests": fake_requests, "requests_toolbelt": fake_toolbelt,
                                          "requests_toolbelt.multipart": fake_multipart,
                                          "requests_toolbelt.multipart.encoder": fake_encoder}):
                uploaded = heygen.asset_upload(source, "fake-key", base / "asset.json", preflight)
                self.assertEqual(uploaded["asset_id"], "asset-1")
                self.assertEqual(source.read_bytes(), b"source-bytes")
                payload = {"video": {"type": "asset_id", "asset_id": "asset-1"},
                           "output_languages": ["English"], "mode": "precision",
                           "translate_audio_only": False, "enable_dynamic_duration": True}
                with patch.object(heygen, "request_json", return_value={"data": {"video_translation_ids": ["job-1"]}}):
                    submitted = heygen.submit_translation(payload, "fake-key", base / "submit.json", preflight,
                        base / "asset.json.result.json")
                self.assertEqual(submitted["video_translation_ids"], ["job-1"])
                proofread_payload = {"video": payload["video"], "output_languages": ["English"],
                                     "title": "Test", "mode": "precision", "enable_video_stretching": True}
                with patch.object(heygen, "request_json", return_value={"data": {"proofread_ids": ["proof-1"]}}):
                    with self.assertRaises(ValueError):
                        heygen.create_proofread(proofread_payload, "fake-key", base / "unreviewed.json", preflight,
                            base / "asset.json.result.json")
                    proof = heygen.create_proofread(proofread_payload, "fake-key", base / "proof.json", preflight,
                        base / "asset.json.result.json", text_path, base / "v1.json", base / "decision.json")
                self.assertEqual(proof["proofread_ids"], ["proof-1"])
                with patch.object(heygen, "request_json", return_value={"data": {"username": "sample", "email": "editor@example.test", "billing_type": "subscription"}}):
                    auth = heygen.auth_check("fake-key", "editor@example.test")
                    with self.assertRaises(ValueError):
                        heygen.auth_check("fake-key", "other@example.test")
                self.assertEqual(auth["transport"], "direct_api_key")
                self.assertTrue(auth["expected_account_verified"])
                self.assertEqual(auth["upload_permission"], "not_verified")
                approved = base / "approved.srt"; approved.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
                srt_asset = base / "srt-asset.json"
                srt_asset.write_text(json.dumps({"status": "uploaded", "asset_id": "srt-1", "sha256": heygen.digest(approved)}))
                with patch.object(heygen, "request_json", return_value={"data": {}}):
                    update = heygen.update_proofread_srt("proof-1", "fake-key", srt_asset, approved, base / "update.json",
                        text_path, preflight, base / "v1.json", base / "decision.json")
                self.assertEqual(update["status"], "updated")
                roundtrip = base / "roundtrip.srt"; roundtrip.write_bytes(approved.read_bytes())
                (base / "roundtrip.srt.receipt.json").write_text(json.dumps({
                    "operation": "proofread_srt", "proofread_id": "proof-1", "sha256": heygen.digest(roundtrip)}))
                with patch.object(heygen, "request_json", return_value={"data": {"video_translation_id": "job-2"}}):
                    generated = heygen.generate_proofread("proof-1", "fake-key", approved,
                        base / "update.json.result.json", roundtrip, base / "generate.json",
                        text_path, preflight, base / "v1.json", base / "decision.json")
                self.assertEqual(generated["response"]["video_translation_id"], "job-2")
                changed = dict(version); changed["source"] = {**version["source"], "original_exact": "已变化"}
                write_new(base / "v2.json", changed)
                with self.assertRaises(ValueError):
                    heygen.generate_proofread("proof-1", "fake-key", approved,
                        base / "update.json.result.json", roundtrip, base / "stale-generate.json",
                        text_path, preflight, base / "v2.json", base / "decision.json")
                self.assertFalse((base / "stale-generate.json").exists())
                roundtrip.write_text("mismatch")
                with self.assertRaises(ValueError):
                    heygen.generate_proofread("proof-1", "fake-key", approved,
                        base / "update.json.result.json", roundtrip, base / "generate-rejected.json",
                        text_path, preflight, base / "v1.json", base / "decision.json")
                with patch.object(heygen, "status", return_value={"status": "completed", "video_url": "https://example.test/video.mp4"}):
                    result = heygen.download("job-1", "fake-key", base / "out.mp4")
                self.assertEqual(result["size_bytes"], len(b"downloaded-video"))
                with self.assertRaises(FileExistsError):
                    heygen.asset_upload(source, "fake-key", base / "asset.json", preflight)
            with self.assertRaises(ValueError):
                heygen.validate_translation({**payload, "translate_audio_only": True})

    def test_youtube_private_upload_and_reconcile(self):
        class Media:
            def __init__(self, path, **kwargs): self.path = path
        http = types.ModuleType("googleapiclient.http"); http.MediaFileUpload = Media
        parent = types.ModuleType("googleapiclient"); parent.http = http
        class Request:
            def next_chunk(self, **kwargs):
                return None, {"id": "video-1", "status": {"privacyStatus": "private"}}
        class Videos:
            def insert(self, **kwargs):
                self.body = kwargs["body"]
                return Request()
        videos = Videos()
        class API:
            def videos(self): return videos
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {"googleapiclient": parent, "googleapiclient.http": http}):
            base = Path(d); source = base / "video.mp4"; source.write_bytes(b"video")
            with patch.object(youtube, "api", return_value=API()), patch.object(youtube, "verify_channel", return_value={"channel_id": "channel-1", "title": "Mine"}), patch.object(youtube, "reconcile", return_value={"video_id": "video-1", "channel_id": "channel-1", "privacyStatus": "private", "title": "Title", "description": "", "tags": []}):
                result = youtube.upload(object(), "channel-1", source, "Title", "", base / "receipt")
            self.assertEqual(videos.body["status"]["privacyStatus"], "private")
            self.assertEqual(result["video_id"], "video-1")
            self.assertEqual(json.loads((base / "receipt/intent.json").read_text())["sha256"], youtube.sha256(source))
            self.assertEqual(source.read_bytes(), b"video")
            self.assertTrue((base / "receipt/reconcile.json").is_file())
            with patch.object(youtube, "api", return_value=API()), patch.object(youtube, "verify_channel", return_value={"channel_id": "channel-1", "title": "Mine"}), patch.object(youtube, "reconcile", return_value={"video_id": "video-2", "channel_id": "channel-1", "privacyStatus": "public", "title": "Title", "description": "", "tags": []}):
                with self.assertRaises(ValueError):
                    youtube.upload(object(), "channel-1", source, "Title", "", base / "receipt-public")
            with patch.object(youtube, "api", return_value=API()), patch.object(youtube, "verify_channel", return_value={"channel_id": "channel-1", "title": "Mine"}), patch.object(youtube, "reconcile", return_value={"video_id": "video-3", "channel_id": "channel-1", "privacyStatus": "private", "title": "Changed", "description": "", "tags": []}):
                with self.assertRaises(ValueError):
                    youtube.upload(object(), "channel-1", source, "Title", "", base / "receipt-mismatch")

    def test_youtube_thumbnail_waits_for_processing(self):
        class Media:
            def __init__(self, path, **kwargs): self.path = path
        http = types.ModuleType("googleapiclient.http"); http.MediaFileUpload = Media
        parent = types.ModuleType("googleapiclient"); parent.http = http
        class ThumbnailRequest:
            def execute(self): return {"items": [{"default": {"url": "https://example.test/cover"}}]}
        class Thumbnails:
            def set(self, **kwargs): return ThumbnailRequest()
        class API:
            def thumbnails(self): return Thumbnails()
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules, {"googleapiclient": parent, "googleapiclient.http": http}):
            root = Path(d)
            image = root / "cover.png"; image.write_bytes(b"mock")
            pending = {"video_id": "v1", "channel_id": "c1", "privacyStatus": "private", "processingStatus": "processing"}
            with patch.object(youtube, "reconcile", return_value=pending):
                with self.assertRaises(ValueError):
                    youtube.set_thumbnail(object(), "c1", "v1", image, root / "receipt.json")
            done = {**pending, "processingStatus": "succeeded", "thumbnails": {"default": {"url": "https://example.test/cover"}}}
            with patch.object(youtube, "reconcile", return_value=done), patch.object(youtube, "api", return_value=API()):
                result = youtube.set_thumbnail(object(), "c1", "v1", image, root / "receipt.json")
            self.assertEqual(result["processingStatus"], "succeeded")

    def test_youtube_project_and_google_account_are_separate_checks(self):
        with tempfile.TemporaryDirectory() as d:
            client = Path(d) / "client.json"
            client.write_text(json.dumps({"installed": {"project_id": "project-1", "client_id": "client-1", "client_secret": "not-logged"}}))
            self.assertEqual(youtube.client_binding(client, "project-1")["client_id"], "client-1")
            with self.assertRaises(ValueError):
                youtube.client_binding(client, "another-project")
        requests = types.ModuleType("google.auth.transport.requests")
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"sub": "subject-1", "email": "owner@example.test", "email_verified": True}
        class Session:
            def __init__(self, creds): pass
            def get(self, url, timeout):
                self.url = url
                return Response()
        requests.AuthorizedSession = Session
        transport = types.ModuleType("google.auth.transport"); transport.requests = requests
        auth = types.ModuleType("google.auth"); auth.transport = transport
        google = types.ModuleType("google"); google.auth = auth
        with patch.dict(sys.modules, {"google": google, "google.auth": auth,
                                      "google.auth.transport": transport, "google.auth.transport.requests": requests}), patch.object(youtube, "verify_channel", return_value={"channel_id": "channel-1", "title": "Mine"}):
            identity = youtube.verify_identity(object(), "channel-1", "owner@example.test", "project-1")
            self.assertTrue(identity["account_verified"])
            with self.assertRaises(ValueError):
                youtube.verify_identity(object(), "channel-1", "wrong@example.test", "project-1")
        class ChannelCall:
            def execute(self): return {"items": [{"id": "other-channel", "snippet": {"title": "Other"}}]}
        class Channels:
            def list(self, **kwargs): return ChannelCall()
        class API:
            def channels(self): return Channels()
        with patch.object(youtube, "api", return_value=API()):
            with self.assertRaises(ValueError):
                youtube.verify_channel(object(), "channel-1")


if __name__ == "__main__": unittest.main()
