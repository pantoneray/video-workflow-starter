import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heygen_web as web
from paid_authorization import create_scope, generate_scope, prepare
from translation_review import human_decision, sha, write_new


class HeyGenWebTests(unittest.TestCase):
    def approve_paid(self, scope, out):
        receipt = prepare(scope, out)
        receipt.update({"billing_type": "subscription", "estimated_credits": 6,
                        "max_expected_credits": 8, "pricing_source": "current account estimate",
                        "reviewer": "human", "approved_at": "2026-11-10T10:00:00+08:00",
                        "decision": "approve", "account_and_billing_confirmed": True,
                        "mode_duration_and_cost_confirmed": True,
                        "actual_charge_may_differ_acknowledged": True})
        out.write_text(json.dumps(receipt), encoding="utf-8")
        return out

    def account(self):
        return {"credential": {"type": "oauth"}, "data": {"email": "editor@example.test", "billing_type": "subscription"}}

    def test_account_mismatch_and_api_key_override(self):
        with patch.object(web, "run_cli", return_value=self.account()):
            self.assertTrue(web.auth_check("editor@example.test")["expected_account_verified"])
            with self.assertRaises(ValueError):
                web.auth_check("other@example.test")
        with patch.dict(web.os.environ, {"HEYGEN_API_KEY": "fake-key"}):
            with self.assertRaises(ValueError):
                web.run_cli(["auth", "status"])

    def test_upload_and_create_only_a_web_draft(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source = base / "source.mp4"; source.write_bytes(b"sample-video")
            preflight = base / "preflight.json"
            text_path = base / "text.txt"; text_path.write_text("Hello\n")
            preflight.write_text(json.dumps({"status": "ready_for_review",
                "purpose": "estimated_pre_heygen_timeline_not_final_audio_alignment",
                "clip_sha256": web.digest(source), "text_sha256": web.digest(text_path), "clip_seconds": 35.0}))
            version = {"version": 1, "source": {"file": "sample.md", "locator": "line 1", "original_exact": "你好"},
                       "target_language": "English", "translation": "Hello", "translation_sha256": sha("Hello"),
                       "independent_translation": "Hello", "blind_backtranslation": "你好", "independent_review": "已核"}
            write_new(base / "v1.json", version)
            write_new(base / "decision.json", human_decision(version, "human", "approve", "核对通过"))
            calls = []
            def fake_cli(args, timeout=180):
                calls.append(args)
                if args[:2] == ["auth", "status"]: return self.account()
                if args[:2] == ["asset", "create"]:
                    return {"data": {"asset_id": "srt-1" if str(args[args.index("--file")+1]).endswith(".srt") else "asset-1"}}
                if args[:3] == ["video-translate", "proofreads", "create"]:
                    return {"data": {"proofread_ids": ["proof-1"]}}
                if args[:4] == ["video-translate", "proofreads", "srt", "update"]:
                    return {"data": {}}
                raise AssertionError(args)
            with patch.object(web, "run_cli", side_effect=fake_cli):
                asset = web.upload_asset(source, preflight, "editor@example.test", base / "asset.json")
                payload = {"video": {"type": "asset_id", "asset_id": asset["asset_id"]},
                    "output_languages": ["English"], "title": "Example", "mode": "precision",
                    "enable_video_stretching": True}
                config = base / "proofread.json"; config.write_text(json.dumps(payload))
                paid = self.approve_paid(create_scope("cli_oauth_proofread_create", "editor@example.test", preflight, config), base / "paid.json")
                draft = web.create_draft(config, preflight, base / "asset.json.result.json",
                                         "editor@example.test", base / "draft.json", text_path,
                                         base / "v1.json", base / "decision.json", paid)
                approved = base / "target.srt"; approved.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
                srt_asset = web.upload_target_srt(approved, text_path, preflight, "editor@example.test", base / "srt-asset.json", base / "v1.json", base / "decision.json")
                wrong = base / "wrong.srt"; wrong.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nDifferent\n")
                with self.assertRaises(ValueError):
                    web.upload_target_srt(wrong, text_path, preflight, "editor@example.test", base / "wrong-asset.json", base / "v1.json", base / "decision.json")
                version["translation"] = "Different"
                write_new(base / "v2.json", version)
                with self.assertRaises(ValueError):
                    web.create_draft(config, preflight, base / "asset.json.result.json",
                                     "editor@example.test", base / "invalid-draft.json", text_path,
                                     base / "v2.json", base / "decision.json", paid)
                with patch.object(web, "remote_srt_bytes", return_value=approved.read_bytes()):
                    updated = web.update_target_srt("proof-1", "editor@example.test", approved,
                        base / "srt-asset.json.result.json", base / "srt-update.json",
                        base / "v1.json", base / "decision.json")
                with self.assertRaises(ValueError):
                    web.update_target_srt("proof-1", "editor@example.test", approved,
                        base / "srt-asset.json.result.json", base / "stale-update.json",
                        base / "v2.json", base / "decision.json")
            self.assertEqual(source.read_bytes(), b"sample-video")
            self.assertFalse(draft["final_generation_submitted"])
            self.assertFalse(draft["web_editor_opened_by_reviewer"])
            self.assertTrue(draft["review_url_candidate"].endswith("/proof-1"))
            self.assertEqual(srt_asset["asset_id"], "srt-1")
            self.assertTrue(updated["roundtrip_exact"])
            self.assertFalse(any("generate" in part for call in calls for part in call))

    def test_generation_requires_current_remote_srt_match(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            approved = base / "approved.srt"; approved.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
            version = {"version": 1, "source": {"file": "sample.md", "locator": "line 1", "original_exact": "你好"},
                       "target_language": "English", "translation": "Hello", "translation_sha256": sha("Hello"),
                       "independent_translation": "Hello", "blind_backtranslation": "你好", "independent_review": "已核"}
            write_new(base / "v1.json", version)
            decision = human_decision(version, "human", "approve", "核对通过")
            write_new(base / "decision.json", decision)
            draft = {"status": "created", "proofread_id": "proof-1", "account_email": "editor@example.test",
                     "mode": "precision", "target_language": "English", "clip_seconds": 35,
                     "clip_sha256": "a" * 64, "text_sha256": "b" * 64,
                     "request_sha256": "c" * 64, "dynamic_duration_requested": True,
                     "review_version_sha256": decision["version_sha256"]}
            write_new(base / "draft.result.json", draft)
            with patch.object(web, "run_cli", return_value=self.account()), patch.object(web, "remote_srt_bytes", return_value=approved.read_bytes()):
                pending = web.prepare_web_review("proof-1", "editor@example.test", approved,
                                                 base / "web-pending.json", base / "v1.json",
                                                 base / "decision.json", base / "draft.result.json")
            self.assertEqual(pending["decision"], "pending")
            self.assertFalse(pending["audio_listened"])
            review = {**pending, "decision": "approve", "web_editor_opened": True, "audio_listened": True,
                      "reviewer": "human", "reviewed_at": "2026-11-10T10:00:00+08:00"}
            write_new(base / "web-review.json", review)
            paid = self.approve_paid(generate_scope("cli_oauth_proofread_generate", "editor@example.test",
                                                     base / "draft.result.json", approved, "proof-1"), base / "paid-generate.json")
            with patch.object(web, "run_cli", return_value=self.account()), patch.object(web, "remote_srt_bytes", return_value=b"different"):
                with self.assertRaises(ValueError):
                    web.generate_reviewed("proof-1", "editor@example.test", approved, base / "rejected.json", base / "web-review.json", base / "draft.result.json", paid, base / "v1.json", base / "decision.json")
            self.assertFalse((base / "rejected.json").exists())
            def fake_cli(args, timeout=180):
                if args[:2] == ["auth", "status"]: return self.account()
                if args[:3] == ["video-translate", "proofreads", "generate"]:
                    return {"data": {"video_translation_id": "video-1"}}
                raise AssertionError(args)
            with patch.object(web, "run_cli", side_effect=fake_cli), patch.object(web, "remote_srt_bytes", return_value=approved.read_bytes()):
                result = web.generate_reviewed("proof-1", "editor@example.test", approved, base / "generate.json", base / "web-review.json", base / "draft.result.json", paid, base / "v1.json", base / "decision.json")
            self.assertEqual(result["video_translation_id"], "video-1")
            review["audio_listened"] = False
            write_new(base / "web-review-bad.json", review)
            with patch.object(web, "run_cli", return_value=self.account()):
                with self.assertRaises(ValueError):
                    web.generate_reviewed("proof-1", "editor@example.test", approved, base / "generate-bad.json", base / "web-review-bad.json", base / "draft.result.json", paid, base / "v1.json", base / "decision.json")
            edited = base / "edited.srt"; edited.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nChanged\n")
            with patch.object(web, "run_cli", return_value=self.account()):
                with self.assertRaisesRegex(ValueError, "偏离当前获批译稿"):
                    web.generate_reviewed("proof-1", "editor@example.test", edited, base / "edited-generate.json", base / "web-review.json", base / "draft.result.json", paid, base / "v1.json", base / "decision.json")
            self.assertFalse((base / "edited-generate.json").exists())

    def test_reapproved_web_edit_generates_from_the_same_draft(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            version = {"version": 1, "source": {"file": "sample.md", "locator": "line 1", "original_exact": "你好"},
                       "target_language": "English", "translation": "Hi", "translation_sha256": sha("Hi"),
                       "independent_translation": "Hello", "blind_backtranslation": "你好", "independent_review": "checked"}
            old_decision = human_decision(version, "human", "approve", "checked")
            draft = {"status": "created", "proofread_id": "proof-1", "account_email": "editor@example.test",
                     "mode": "precision", "target_language": "English", "clip_seconds": 35,
                     "clip_sha256": "a" * 64, "text_sha256": "b" * 64, "request_sha256": "c" * 64,
                     "dynamic_duration_requested": True, "review_version_sha256": old_decision["version_sha256"]}
            draft_path = base / "draft.json"; write_new(draft_path, draft)
            original_draft = draft_path.read_bytes()
            version.update(version=2, translation="Hello", translation_sha256=sha("Hello"))
            write_new(base / "v2.json", version)
            write_new(base / "old-decision.json", old_decision)
            write_new(base / "decision.json", human_decision(version, "human", "approve", "approved web edit"))
            srt = base / "reviewed.srt"; srt.write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nHello\n")
            calls = []
            def cli(args, timeout=180):
                calls.append(args)
                if args[:2] == ["auth", "status"]: return self.account()
                if args[:3] == ["video-translate", "proofreads", "generate"]:
                    return {"data": {"video_translation_id": "video-2"}}
                raise AssertionError(args)
            with patch.object(web, "run_cli", side_effect=cli), patch.object(web, "remote_srt_bytes", return_value=srt.read_bytes()):
                with self.assertRaises(ValueError):
                    web.prepare_web_review("proof-1", "editor@example.test", srt, base / "bad.json",
                                           base / "v2.json", base / "old-decision.json", draft_path)
                review = web.prepare_web_review("proof-1", "editor@example.test", srt, base / "pending.json",
                                                base / "v2.json", base / "decision.json", draft_path)
                review.update(decision="approve", reviewer="human", web_editor_opened=True,
                              audio_listened=True, reviewed_at="2026-11-10T12:00:00+08:00")
                write_new(base / "review.json", review)
                paid = self.approve_paid(generate_scope("cli_oauth_proofread_generate", "editor@example.test",
                                         draft_path, srt, "proof-1"), base / "paid.json")
                result = web.generate_reviewed("proof-1", "editor@example.test", srt, base / "generate.json",
                    base / "review.json", draft_path, paid, base / "v2.json", base / "decision.json")
            self.assertEqual(result["proofread_id"], "proof-1")
            self.assertEqual(result["draft_receipt_sha256"], web.digest(draft_path))
            self.assertEqual(draft_path.read_bytes(), original_draft)
            self.assertFalse(any("create" in call for call in calls))


if __name__ == "__main__": unittest.main()
