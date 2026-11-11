import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from paid_authorization import claim, create_scope, generate_scope, prepare, verify


class PaidAuthorizationTests(unittest.TestCase):
    def test_specific_scope_and_manual_fields(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            preflight = root / "preflight.json"
            preflight.write_text(json.dumps({"status": "ready_for_review", "clip_seconds": 35,
                                            "clip_sha256": "a" * 64, "text_sha256": "b" * 64}))
            payload = root / "payload.json"
            payload.write_text(json.dumps({"mode": "precision", "output_languages": ["English"],
                                           "enable_video_stretching": True}))
            scope = create_scope("cli_oauth_proofread_create", "EDITOR@example.test", preflight, payload)
            path = root / "decision.json"
            pending = prepare(scope, path)
            with self.assertRaises(ValueError):
                verify(path, scope, "subscription")
            pending.update({"billing_type": "subscription", "estimated_credits": 6,
                            "max_expected_credits": 8, "pricing_source": "account UI estimate",
                            "reviewer": "actual person", "approved_at": "2026-11-10T10:00:00+08:00",
                            "decision": "approve", "account_and_billing_confirmed": True,
                            "mode_duration_and_cost_confirmed": True,
                            "actual_charge_may_differ_acknowledged": True})
            path.write_text(json.dumps(pending))
            self.assertEqual(verify(path, scope, "subscription")["decision"], "approve")
            self.assertTrue(claim(path, scope).is_file())
            with self.assertRaises(FileExistsError):
                claim(path, scope)
            for changed in ({"mode": "speed"}, {"clip_seconds": 36}, {"account_email": "other@example.test"}):
                with self.assertRaises(ValueError):
                    verify(path, {**scope, **changed}, "subscription")
            with self.assertRaises(ValueError):
                verify(path, scope, "pay_as_you_go")
            payload.write_text(json.dumps({"mode": "speed", "output_languages": ["English"],
                                           "enable_video_stretching": True}))
            with self.assertRaises(ValueError):
                verify(path, create_scope("cli_oauth_proofread_create", "editor@example.test", preflight, payload), "subscription")

    def test_generation_binds_draft_and_srt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            draft = root / "draft.json"
            draft.write_text(json.dumps({"status": "created", "proofread_id": "p1",
                "account_email": "editor@example.test", "mode": "precision", "target_language": "English",
                "clip_seconds": 35, "clip_sha256": "a" * 64, "text_sha256": "b" * 64,
                "request_sha256": "c" * 64, "dynamic_duration_requested": True}))
            srt = root / "approved.srt"; srt.write_text("approved")
            scope = generate_scope("cli_oauth_proofread_generate", "editor@example.test", draft, srt, "p1")
            self.assertEqual(scope["proofread_id"], "p1")
            with self.assertRaises(ValueError):
                generate_scope("cli_oauth_proofread_generate", "other@example.test", draft, srt, "p1")
            with self.assertRaises(ValueError):
                generate_scope("cli_oauth_proofread_generate", "editor@example.test", draft, srt, "p2")


if __name__ == "__main__": unittest.main()
