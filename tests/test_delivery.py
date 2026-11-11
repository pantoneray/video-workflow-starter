import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from delivery import ROLES, init, add, attest, embedded_local_paths, verify
from translation_review import human_decision, sha, version_digest, write_new
from publication_review import decide
from check_output import sha256
from prepare_upload_video import prepare as prepare_upload


class DeliveryTests(unittest.TestCase):
    def test_copied_json_reports_embedded_local_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "receipt.json"
            source.write_text(json.dumps({"source_file": "/another/mac/source.mp4"}))
            run = base / "task-paths"
            init(run, "task-paths")
            record = add(run, "source", source, copy=True)
            self.assertTrue(record["embedded_local_paths"])
            self.assertTrue(record["portable"])
            self.assertEqual(len(verify(run)["local_dependencies"]), 1)
            source.write_text(json.dumps({"source_file": "C:\\Media\\source.mp4"}))
            self.assertTrue(embedded_local_paths(source))

    def test_inventory_is_not_final_handoff_without_human_attestation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            run = base / "task-2"
            init(run, "task-2")
            for role in ROLES:
                item = base / f"{role}.txt"
                item.write_text(role)
                add(run, role, item, copy=True)
            status = verify(run)
            self.assertTrue(status["artifact_inventory_complete"])
            self.assertFalse(status["production_evidence_complete"])
            self.assertFalse(status["handoff_complete"])
            checks = {name: True for name in
                      ("sources_and_translation_checked", "clips_and_video_played",
                       "subtitles_and_qc_checked", "publication_and_cover_checked",
                       "youtube_private_video_and_cover_seen")}
            with self.assertRaises(ValueError):
                attest(run, "reviewer", "checked", {**checks, "youtube_private_video_and_cover_seen": False})
            with self.assertRaises(ValueError):
                attest(run, "reviewer", "actual review recorded", checks)
            self.assertFalse((run / "handoff-attestation.json").exists())
            extra = base / "another-source.txt"; extra.write_text("new")
            add(run, "source", extra)
            self.assertFalse(verify(run)["human_handoff_attested"])
            (run / "cover" / "cover.txt").write_text("changed")
            self.assertFalse(verify(run)["handoff_complete"])

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "完整交付样本需可选 Pillow 包装依赖")
    def test_linked_evidence_and_attestation_invalidate_on_change(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            run = base / "delivery"
            init(run, "synthetic-1")
            video = base / "video.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=320x320:r=24:d=35", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=35", "-c:v", "libx264", "-c:a", "aac",
                            "-shortest", str(video)], check=True, timeout=120)
            video_hash = sha256(video)
            upload_copy = base / "upload-copy.mp4"
            prepare_upload(video, upload_copy)
            upload_hash = sha256(upload_copy)
            upload_copy_receipt = Path(str(upload_copy) + ".receipt.json")
            source = {"file": "sample.md", "locator": "line 1", "source_sha256": "a" * 64,
                      "original_exact": "你好", "version": 1}
            version = {"version": 1, "source": source, "translation": "Hello",
                       "translation_sha256": sha("Hello"), "independent_translation": "Hello",
                       "blind_backtranslation": "你好", "independent_review": "checked"}
            approval = human_decision(version, "translator", "approve", "reviewed")
            candidate_source = base / "source.json"
            write_new(candidate_source, {"results": [source]})
            version_path = base / "version.json"; write_new(version_path, version)
            approval_path = base / "approval.json"; write_new(approval_path, approval)
            srt = base / "final.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            target_text = base / "target.txt"; target_text.write_text("Hello\n", encoding="utf-8")
            clip_manifest = base / "manifest.json"
            write_new(clip_manifest, {"segments": [{"sha256": video_hash, "duration": 35}]})
            heygen_receipt = base / "heygen.json"
            write_new(heygen_receipt, {"status": "downloaded", "sha256": video_hash,
                                      "job_id": "job-1", "account_email": "editor@example.test"})
            preflight = base / "preflight.json"
            write_new(preflight, {"status": "ready_for_review",
                                  "purpose": "estimated_pre_heygen_timeline_not_final_audio_alignment",
                                  "clip_sha256": upload_hash, "text_sha256": sha256(target_text)})
            asset = base / "asset.json"
            write_new(asset, {"status": "uploaded", "asset_id": "asset-1", "sha256": upload_hash,
                              "account_email": "editor@example.test"})
            draft = base / "draft.json"
            write_new(draft, {"operation": "cli_oauth_proofread_create", "status": "created",
                              "proofread_id": "proof-1", "clip_sha256": upload_hash,
                              "review_version_sha256": version_digest(version),
                              "account_email": "editor@example.test"})
            reviewed = base / "reviewed.srt"; reviewed.write_bytes(srt.read_bytes())
            web_review = base / "web-review.json"
            write_new(web_review, {"proofread_id": "proof-1", "account_email": "editor@example.test", "decision": "approve",
                                   "web_editor_opened": True, "audio_listened": True, "reviewer": "human",
                                   "srt_sha256": sha256(reviewed),
                                   "review_version_sha256": version_digest(version)})
            generate = base / "generate.json"
            write_new(generate, {"operation": "cli_oauth_proofread_generate", "status": "submitted",
                                 "proofread_id": "proof-1", "video_translation_id": "job-1",
                                 "srt_sha256": sha256(reviewed),
                                 "review_version_sha256": version_digest(version),
                                 "account_email": "editor@example.test"})
            package_receipt = base / "package.json"
            write_new(package_receipt, {"source_sha256": video_hash, "subtitle_sha256": sha256(srt),
                                        "output_qc": {"sha256": video_hash, "decode": "PASS"}})
            qc = base / "qc.json"
            write_new(qc, {"video_sha256": video_hash, "aligned_srt_sha256": sha256(srt),
                           "flagged_cues": [], "manual_review": {"reviewer": "listener",
                           "reviewed_at": "2026-11-10T10:00:00+08:00", "voice_match": True,
                           "lip_sync": True, "audio_video_sync": True, "speech_natural": True,
                           "start_end_ok": True}})
            cover = base / "cover.png"
            Image.new("RGB", (320, 320), "blue").save(cover)
            candidate = base / "candidate.json"
            write_new(candidate, {"status": "pending_human_review", "version": 1,
                                  "version_sha256": version_digest(version),
                                  "translation_sha256": sha("Hello"), "title": "Hello",
                                  "description": "A short sample", "tags": ["sample"], "cover_text": "Hello"})
            decision = base / "publication.json"
            decide(candidate, version_path, approval_path, video, cover, "publisher", "approve",
                   "checked sample", decision)
            upload = base / "upload-verified.json"
            write_new(upload, {"video_id": "v1", "channel_id": "c1", "privacyStatus": "private",
                               "sha256": video_hash, "publication_candidate_sha256": version_digest(json.loads(candidate.read_text())),
                               "title": "Hello", "description": "A short sample", "tags": ["sample"],
                               "google_account_email": "owner@example.test", "gcp_project_id": "project-1"})
            processing = base / "processing.json"
            write_new(processing, {"video_id": "v1", "channel_id": "c1", "privacyStatus": "private",
                                   "processingStatus": "succeeded", "google_account_email": "owner@example.test",
                                   "gcp_project_id": "project-1"})
            thumbnail = base / "thumbnail.json"
            write_new(thumbnail, {"video_id": "v1", "channel_id": "c1", "processingStatus": "succeeded",
                                  "image_sha256": sha256(cover), "remote_thumbnails": {"default": {}},
                                  "publication_candidate_sha256": version_digest(json.loads(candidate.read_text())),
                                  "upload_receipt_sha256": sha256(upload)})
            for role, files in {"source": [candidate_source], "translation": [version_path, approval_path],
                                "clips": [video, clip_manifest], "subtitles": [srt, target_text],
                                "heygen": [upload_copy, upload_copy_receipt, video, heygen_receipt,
                                           preflight, asset, draft, reviewed, web_review, generate],
                                "packaging": [video, package_receipt],
                                "cover": [cover], "metadata": [candidate, decision], "qc": [qc],
                                "youtube": [upload, processing, thumbnail]}.items():
                for file in files:
                    add(run, role, file, copy=True)
            status = verify(run)
            self.assertTrue(status["production_evidence_complete"], status["evidence_issues"])
            self.assertFalse(status["handoff_complete"])
            api_update = base / "api-srt-update.json"
            write_new(api_update, {"operation": "proofread_srt_update", "status": "updated",
                                   "proofread_id": "proof-1", "srt_sha256": sha256(reviewed),
                                   "review_version_sha256": version_digest(version)})
            api_roundtrip = base / "api-srt-roundtrip.json"
            write_new(api_roundtrip, {"operation": "proofread_srt", "proofread_id": "proof-1",
                                      "sha256": sha256(reviewed)})
            add(run, "heygen", api_update, copy=True)
            add(run, "heygen", api_roundtrip, copy=True)
            manifest_file = run / "delivery-manifest.json"
            manifest_data = json.loads(manifest_file.read_text())
            copied_draft = run / "heygen" / "draft.json"
            copied_generate = run / "heygen" / "generate.json"
            # Web text may be reapproved after this original draft was created.
            draft_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "heygen/draft.json")
            generate_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "heygen/generate.json")
            copied_draft.write_text(json.dumps({**json.loads(draft.read_text()),
                                               "review_version_sha256": "earlier-approved-version"}))
            draft_entry["sha256"] = sha256(copied_draft)
            copied_generate.write_text(json.dumps({**json.loads(generate.read_text()),
                "draft_receipt_sha256": sha256(copied_draft),
                "draft_review_version_sha256": "earlier-approved-version"}))
            generate_entry["sha256"] = sha256(copied_generate)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            revised = verify(run)
            self.assertTrue(revised["production_evidence_complete"], revised["evidence_issues"])
            copied_generate.write_bytes(generate.read_bytes())
            generate_entry["sha256"] = sha256(copied_generate)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            self.assertFalse(verify(run)["production_evidence_complete"])
            copied_draft.write_text(json.dumps({**json.loads(draft.read_text()),
                                               "operation": "proofread_create"}))
            copied_generate.write_text(json.dumps({**json.loads(generate.read_text()),
                                                  "operation": "proofread_generate"}))
            draft_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "heygen/draft.json")
            generate_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "heygen/generate.json")
            draft_entry["sha256"] = sha256(copied_draft)
            generate_entry["sha256"] = sha256(copied_generate)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            self.assertTrue(verify(run)["production_evidence_complete"], verify(run)["evidence_issues"])
            copied_draft.write_bytes(draft.read_bytes())
            copied_generate.write_bytes(generate.read_bytes())
            draft_entry["sha256"] = sha256(copied_draft)
            generate_entry["sha256"] = sha256(copied_generate)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            copied_draft.write_text(json.dumps({**json.loads(draft.read_text()), "clip_sha256": "other-video"}))
            draft_entry["sha256"] = sha256(copied_draft)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            self.assertTrue(verify(run)["all_registered_files_valid"])
            self.assertFalse(verify(run)["production_evidence_complete"])
            copied_draft.write_bytes(draft.read_bytes())
            draft_entry["sha256"] = sha256(copied_draft)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            copied_processing = run / "youtube" / "processing.json"
            copied_processing.write_text(json.dumps({**json.loads(processing.read_text()),
                                                      "privacyStatus": "public"}), encoding="utf-8")
            processed_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "youtube/processing.json")
            processed_entry["sha256"] = sha256(copied_processing)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            self.assertTrue(verify(run)["all_registered_files_valid"])
            self.assertFalse(verify(run)["production_evidence_complete"])
            copied_processing.write_bytes(processing.read_bytes())
            processed_entry["sha256"] = sha256(copied_processing)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            copied_thumbnail = run / "youtube" / "thumbnail.json"
            thumbnail_data = json.loads(copied_thumbnail.read_text())
            copied_thumbnail.write_text(json.dumps({**thumbnail_data, "upload_receipt_sha256": "wrong"}))
            thumbnail_entry = next(x for x in manifest_data["artifacts"] if x["path"] == "youtube/thumbnail.json")
            thumbnail_entry["sha256"] = sha256(copied_thumbnail)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            self.assertTrue(verify(run)["all_registered_files_valid"])
            self.assertFalse(verify(run)["production_evidence_complete"])
            copied_thumbnail.write_bytes(thumbnail.read_bytes())
            thumbnail_entry["sha256"] = sha256(copied_thumbnail)
            manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
            checks = {name: True for name in
                      ("sources_and_translation_checked", "clips_and_video_played",
                       "subtitles_and_qc_checked", "publication_and_cover_checked",
                       "youtube_private_video_and_cover_seen")}
            self.assertTrue(attest(run, "reviewer", "synthetic offline evidence", checks)["handoff_complete"])
            (run / "youtube" / "processing.json").write_text("{}", encoding="utf-8")
            self.assertFalse(verify(run)["handoff_complete"])

    def test_copy_link_hash_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "clip.mp4"; source.write_bytes(b"example")
            run = base / "task-1"
            init(run, "task-1")
            copied = add(run, "clips", source, copy=True)
            self.assertTrue(copied["portable"])
            self.assertEqual(add(run, "clips", source, copy=True)["status"], "already_recorded")
            local = add(run, "source", source)
            self.assertFalse(local["portable"])
            self.assertEqual(source.read_bytes(), b"example")
            self.assertTrue(verify(run)["all_portable_files_valid"])
            self.assertFalse(verify(run)["handoff_complete"])
            self.assertIn("translation", verify(run)["missing_roles"])
            (run / "clips" / "clip.mp4").write_bytes(b"altered")
            self.assertFalse(verify(run)["all_portable_files_valid"])


if __name__ == "__main__":
    unittest.main()
