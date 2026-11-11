#!/usr/bin/env python3
"""Create a versioned task handoff with explicit portable/local artifact status."""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("source", "translation", "clips", "subtitles", "heygen", "packaging",
         "cover", "metadata", "qc", "youtube")
HANDOFF_CHECKS = ("sources_and_translation_checked", "clips_and_video_played",
                  "subtitles_and_qc_checked", "publication_and_cover_checked",
                  "youtube_private_video_and_cover_seen")
WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as item:
        for block in iter(lambda: item.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def manifest_path(root):
    return Path(root) / "delivery-manifest.json"


def attestation_path(root):
    return Path(root) / "handoff-attestation.json"


def manifest_sha256(root):
    return digest(manifest_path(root))


def embedded_local_paths(path):
    if Path(path).suffix.lower() != ".json":
        return False
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return False

    def check(item):
        if isinstance(item, dict):
            return any(check(value) for value in item.values())
        if isinstance(item, list):
            return any(check(value) for value in item)
        return isinstance(item, str) and (item.startswith("/") or bool(WINDOWS_ABSOLUTE.match(item)))

    return check(value)


def init(root, task_id):
    root = Path(root)
    if root.exists() or not task_id.strip():
        raise ValueError("交付目录已存在或任务 ID 为空；每次运行使用新目录")
    root.mkdir(parents=True)
    for role in ROLES:
        (root / role).mkdir()
    data = {"task_id": task_id, "artifacts": [], "handoff_rule": "copied files can be handed off; local references need original paths/software/accounts"}
    manifest_path(root).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def add(root, role, source, copy=False, label=""):
    root = Path(root)
    source = Path(source).expanduser().resolve()
    if role not in ROLES or not source.is_file():
        raise ValueError("角色无效或文件不存在")
    data = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    fingerprint = digest(source)
    if any(item["role"] == role and item["sha256"] == fingerprint for item in data["artifacts"]):
        return {"status": "already_recorded", "sha256": fingerprint}
    target = root / role / source.name
    if copy:
        if target.exists():
            raise FileExistsError("目标文件同名已存在；请改名或换新运行目录")
        shutil.copy2(source, target)
        if digest(target) != fingerprint:
            target.unlink(missing_ok=True)
            raise RuntimeError("复制后哈希不一致")
        reference = str(target.relative_to(root))
    else:
        reference = str(source)
    embedded = embedded_local_paths(source)
    entry = {"role": role, "label": label, "sha256": fingerprint, "size": source.stat().st_size,
             "path": reference, "portable": bool(copy),
             "embedded_local_paths": embedded,
             "dependency": ("requires original local file" if not copy else
                            "embedded paths may require original files for re-editing" if embedded else "none")}
    data["artifacts"].append(entry)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, delete=False) as item:
            json.dump(data, item, ensure_ascii=False, indent=2)
            item.write("\n")
            temp = Path(item.name)
        os.replace(temp, manifest_path(root))
    finally:
        if temp and temp.exists():
            temp.unlink()
    return entry


def evidence_check(root, data, checks):
    """Validate links between the registered production artifacts, offline."""
    if any(item["status"] != "PASS" for item in checks):
        return ["已登记文件缺失或变化"]
    by_role = {role: [] for role in ROLES}
    for entry in data["artifacts"]:
        path = Path(root) / entry["path"] if entry["portable"] else Path(entry["path"])
        by_role[entry["role"]].append(path)
    missing = [role for role in ROLES if not by_role[role]]
    if missing:
        return ["缺少交付角色：" + ", ".join(missing)]
    from check_output import inspect
    from publication_review import checked_cover, verify as verify_publication
    from subtitle_tools import full_text, normalized, parse_srt
    from translation_review import load, verify_approval
    issues = []

    def jsons(role):
        values = []
        for path in by_role[role]:
            if path.suffix.lower() == ".json":
                try:
                    value = load(path)
                    if isinstance(value, dict):
                        values.append((path, value))
                except (OSError, ValueError):
                    pass
        return values

    def first(role, predicate):
        return next(((path, value) for path, value in jsons(role) if predicate(value)), None)

    version = first("translation", lambda x: isinstance(x.get("source"), dict) and "translation" in x)
    approval = first("translation", lambda x: x.get("decision") == "approve" and "version_sha256" in x)
    if not version or not approval:
        issues.append("译稿版本和明确批准记录缺失")
        return issues
    try:
        verified = verify_approval(version[1], approval[1])
    except (ValueError, KeyError, TypeError):
        issues.append("译稿批准与当前版本不一致")
        return issues
    source = version[1]["source"]
    if not all(source.get(key) for key in ("original_exact", "source_sha256", "file", "locator")):
        issues.append("批准译稿缺可核对的原文出处或文件哈希")
    if not any(any(isinstance(item, dict)
                       and item.get("original_exact") == source.get("original_exact")
                       and item.get("source_sha256") == source.get("source_sha256")
                       and item.get("file") == source.get("file")
                       and item.get("locator") == source.get("locator")
                       for item in value.get("results", []))
               for _, value in jsons("source") if isinstance(value.get("results"), list)):
        issues.append("选文出处候选与批准译稿不一致")

    srt = next((path for path in by_role["subtitles"] if path.suffix.lower() == ".srt"), None)
    try:
        if not srt or normalized(full_text(parse_srt(srt))) != normalized(version[1]["translation"]):
            issues.append("最终字幕与批准译文不一致")
    except (ValueError, OSError):
        issues.append("最终字幕无法读取或解析")

    clip = next((path for path in by_role["clips"] if path.suffix.lower() in (".mp4", ".mov")), None)
    manifest = first("clips", lambda x: isinstance(x.get("segments"), list))
    try:
        clip_qc = inspect(clip) if clip else None
        if (not clip or not manifest or not clip_qc or clip_qc["decode"] != "PASS"
                or not clip_qc["video"] or not 30 <= clip_qc["duration_s"] <= 45
                or not any(isinstance(x, dict) and x.get("sha256") == digest(clip)
                           and abs(float(x.get("duration", 0)) - clip_qc["duration_s"]) <= .5
                           for x in manifest[1]["segments"])):
            issues.append("30–45 秒切片与裁切清单不匹配")
    except (OSError, ValueError, RuntimeError):
        issues.append("切片技术检查失败")

    current_text_hashes = set()
    for path in by_role["subtitles"]:
        if path.suffix.lower() == ".txt":
            try:
                if normalized(path.read_text(encoding="utf-8-sig")) == normalized(version[1]["translation"]):
                    current_text_hashes.add(digest(path))
            except (OSError, UnicodeError):
                pass
    preflight = first("heygen", lambda x: x.get("purpose") == "estimated_pre_heygen_timeline_not_final_audio_alignment"
                      and x.get("text_sha256") in current_text_hashes)
    asset = first("heygen", lambda x: x.get("status") == "uploaded" and "asset_id" in x
                  and preflight and x.get("sha256") == preflight[1].get("clip_sha256"))
    draft = first("heygen", lambda x: x.get("status") == "created" and
                  x.get("operation") in ("cli_oauth_proofread_create", "proofread_create"))
    generated = first("heygen", lambda x: x.get("status") == "submitted" and
                      x.get("operation") in ("cli_oauth_proofread_generate", "proofread_generate"))
    heygen_receipt = first("heygen", lambda x: x.get("status") == "downloaded" and "sha256" in x)
    heygen_video = (next((path for path in by_role["heygen"] if path.suffix.lower() == ".mp4"
                          and digest(path) == heygen_receipt[1]["sha256"]), None)
                    if heygen_receipt else None)
    if not (preflight and asset and draft and generated and heygen_receipt and clip):
        issues.append("HeyGen 预检、资产、草稿、生成或下载回执缺失")
    else:
        report, uploaded_asset, session, job, downloaded = (preflight[1], asset[1], draft[1],
                                                             generated[1], heygen_receipt[1])
        proofread_id = session.get("proofread_id") or next(iter(session.get("proofread_ids") or []), None)
        generation_id = (job.get("video_translation_id") or
                         (job.get("response") or {}).get("video_translation_id") or
                         next(iter((job.get("response") or {}).get("video_translation_ids") or []), None))
        upload_hash = report.get("clip_sha256")
        target_text = next((path for path in by_role["subtitles"] if path.suffix.lower() == ".txt"
                            and digest(path) == report.get("text_sha256")), None)
        upload_copy = next((path for path in by_role["heygen"] if path.suffix.lower() == ".mp4"
                            and digest(path) == upload_hash), None)
        copy_receipt = first("heygen", lambda x: x.get("status") == "local_upload_copy_ready_not_remote_accepted"
                             and x.get("output_sha256") == upload_hash)
        reviewed_srt = next((path for path in by_role["heygen"] if path.suffix.lower() == ".srt"
                             and digest(path) == job.get("srt_sha256")), None)
        try:
            text_matches = bool(target_text and
                normalized(target_text.read_text(encoding="utf-8-sig")) == normalized(version[1]["translation"]))
            reviewed_matches = bool(reviewed_srt and
                normalized(full_text(parse_srt(reviewed_srt))) == normalized(version[1]["translation"]))
        except (OSError, UnicodeError, ValueError):
            text_matches = reviewed_matches = False
        draft_version_matches = session.get("review_version_sha256") == verified["version_sha256"]
        if session.get("operation") == "cli_oauth_proofread_create" and not draft_version_matches:
            draft_version_matches = bool(
                job.get("draft_receipt_sha256") == digest(draft[0])
                and job.get("draft_review_version_sha256") == session.get("review_version_sha256"))
        if (report.get("status") != "ready_for_review" or not text_matches
                or uploaded_asset.get("sha256") != upload_hash
                or session.get("clip_sha256") != upload_hash
                or not draft_version_matches
                or job.get("review_version_sha256") != verified["version_sha256"]
                or not proofread_id or job.get("proofread_id") != proofread_id
                or not generation_id or downloaded.get("job_id") != generation_id
                or not reviewed_matches
                or (upload_hash != digest(clip) and
                    (not upload_copy or not copy_receipt
                     or copy_receipt[1].get("source_sha256") != digest(clip)))):
            issues.append("HeyGen 原切片、上传副本、预检、译稿、资产、草稿、生成与下载不成链")
        elif session.get("operation") == "cli_oauth_proofread_create":
            web_review = first("heygen", lambda x: x.get("proofread_id") == proofread_id and
                               x.get("web_editor_opened") is True and x.get("audio_listened") is True)
            if (not web_review or web_review[1].get("decision") != "approve"
                    or not web_review[1].get("reviewer")
                    or web_review[1].get("srt_sha256") != digest(reviewed_srt)
                    or web_review[1].get("review_version_sha256") != verified["version_sha256"]
                    or web_review[1].get("account_email") != session.get("account_email")
                    or (uploaded_asset.get("account_email") and
                        uploaded_asset.get("account_email") != session.get("account_email"))
                    or session.get("account_email") != job.get("account_email")
                    or session.get("account_email") != downloaded.get("account_email")):
                issues.append("HeyGen 网页试听审核或同账号生成回执不成链")
        else:
            updated = first("heygen", lambda x: x.get("operation") == "proofread_srt_update"
                            and x.get("status") == "updated")
            roundtrip = first("heygen", lambda x: x.get("operation") == "proofread_srt"
                              and x.get("proofread_id") == proofread_id)
            if (not updated or updated[1].get("proofread_id") != proofread_id
                    or updated[1].get("srt_sha256") != digest(reviewed_srt)
                    or updated[1].get("review_version_sha256") != verified["version_sha256"]
                    or not roundtrip or roundtrip[1].get("sha256") != digest(reviewed_srt)):
                issues.append("HeyGen API 备用路线缺当前 Proofread SRT 更新回执")
    try:
        heygen_qc = inspect(heygen_video) if heygen_video else None
    except (OSError, ValueError, RuntimeError):
        heygen_qc = None
    if (not heygen_video or not heygen_receipt or heygen_receipt[1]["sha256"] != digest(heygen_video)
            or not heygen_qc or heygen_qc["decode"] != "PASS" or not heygen_qc["video"] or not heygen_qc["audio"]):
        issues.append("HeyGen 下载成片与回执不匹配")
    final = next((path for path in by_role["packaging"] if path.suffix.lower() == ".mp4"), None)
    package_receipt = first("packaging", lambda x: "output_qc" in x and "subtitle_sha256" in x)
    try:
        final_qc = inspect(final) if final else None
        if (not final or not package_receipt or not srt or not heygen_video
                or package_receipt[1]["subtitle_sha256"] != digest(srt)
                or package_receipt[1]["source_sha256"] != digest(heygen_video)
                or package_receipt[1]["output_qc"]["sha256"] != digest(final)
                or not final_qc or final_qc["decode"] != "PASS" or not final_qc["video"] or not final_qc["audio"]):
            issues.append("包装成片与源片、字幕或包装回执不匹配")
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        issues.append("包装成片技术检查失败")

    qc = first("qc", lambda x: "manual_review" in x and "video_sha256" in x)
    if qc:
        review = qc[1]["manual_review"] if isinstance(qc[1]["manual_review"], dict) else {}
        try:
            reviewed = datetime.fromisoformat(str(review.get("reviewed_at")))
            valid = (reviewed.tzinfo is not None and bool(review.get("reviewer"))
                     and all(review.get(k) is True for k in
                             ("voice_match", "lip_sync", "audio_video_sync", "speech_natural", "start_end_ok"))
                     and (not qc[1].get("flagged_cues") or bool(review.get("rate_exception_reason")))
                     and heygen_video and qc[1]["video_sha256"] == digest(heygen_video)
                     and srt and qc[1]["aligned_srt_sha256"] == digest(srt))
        except (ValueError, KeyError, TypeError, OSError):
            valid = False
    else:
        valid = False
    if not valid:
        issues.append("HeyGen 成片人工听审或字幕绑定记录缺失")

    cover = next((path for path in by_role["cover"] if path.suffix.lower() in (".png", ".jpg", ".jpeg")), None)
    try:
        checked_cover(cover)
    except (ValueError, OSError):
        issues.append("实际封面图缺失或无效")

    candidate = first("metadata", lambda x: x.get("status") == "pending_human_review" and "title" in x)
    decision = first("metadata", lambda x: x.get("decision") == "approve" and "candidate_sha256" in x)
    publication = None
    if candidate and decision and final and cover:
        try:
            publication = verify_publication(candidate[0], decision[0], version[0], approval[0], cover, final)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError):
            pass
    if not publication or publication["version_sha256"] != verified["version_sha256"]:
        issues.append("发布资料批准与成片、封面或译稿版本不匹配")

    uploaded = first("youtube", lambda x: x.get("privacyStatus") == "private" and "publication_candidate_sha256" in x)
    processed = first("youtube", lambda x: x.get("processingStatus") == "succeeded" and x.get("privacyStatus") == "private")
    thumbnail = first("youtube", lambda x: "image_sha256" in x and "remote_thumbnails" in x)
    if not (uploaded and processed and thumbnail and publication and final and cover
            and uploaded[1].get("sha256") == digest(final)
            and uploaded[1].get("publication_candidate_sha256") == publication["candidate_sha256"]
            and uploaded[1].get("title") == publication["title"]
            and uploaded[1].get("description") == publication["description"]
            and uploaded[1].get("tags") == publication["tags"]
            and uploaded[1].get("video_id") == processed[1].get("video_id") == thumbnail[1].get("video_id")
            and uploaded[1].get("channel_id") == processed[1].get("channel_id") == thumbnail[1].get("channel_id")
            and uploaded[1].get("google_account_email") == processed[1].get("google_account_email")
            and uploaded[1].get("gcp_project_id") == processed[1].get("gcp_project_id")
            and thumbnail[1].get("processingStatus") == "succeeded"
            and thumbnail[1].get("publication_candidate_sha256") == publication["candidate_sha256"]
            and thumbnail[1].get("upload_receipt_sha256") == digest(uploaded[0])
            and thumbnail[1].get("image_sha256") == digest(cover)):
        issues.append("YouTube 私密上传、处理完成和封面回执不成链")
    return issues


def verify(root):
    root = Path(root)
    data = json.loads(manifest_path(root).read_text(encoding="utf-8"))
    checks = []
    for entry in data["artifacts"]:
        path = root / entry["path"] if entry["portable"] else Path(entry["path"])
        status = "PASS" if path.is_file() and digest(path) == entry["sha256"] else "MISSING_OR_CHANGED"
        checks.append({"role": entry["role"], "path": entry["path"], "portable": entry["portable"],
                       "embedded_local_paths": entry.get("embedded_local_paths", False), "status": status})
    missing_roles = [role for role in ROLES if not any(item["role"] == role and item["status"] == "PASS" for item in checks)]
    all_valid = all(item["status"] == "PASS" for item in checks)
    inventory_complete = all_valid and not missing_roles
    evidence_issues = evidence_check(root, data, checks) if inventory_complete else []
    evidence_complete = inventory_complete and not evidence_issues
    if attestation_path(root).is_file():
        try:
            attestation = json.loads(attestation_path(root).read_text(encoding="utf-8"))
            reviewed = datetime.fromisoformat(str(attestation.get("reviewed_at")))
            attested = (reviewed.tzinfo is not None and attestation.get("task_id") == data["task_id"]
                        and attestation.get("manifest_sha256") == manifest_sha256(root)
                        and attestation.get("reviewer") and attestation.get("notes")
                        and all(attestation.get(name) is True for name in HANDOFF_CHECKS))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            attested = False
    else:
        attested = False
    return {"task_id": data["task_id"], "checks": checks,
            "all_portable_files_valid": all(item["status"] == "PASS" for item in checks if item["portable"]),
            "all_registered_files_valid": all_valid, "missing_roles": missing_roles,
            "artifact_inventory_complete": inventory_complete,
            "production_evidence_complete": evidence_complete, "evidence_issues": evidence_issues,
            "human_handoff_attested": bool(attested),
            "handoff_complete": bool(evidence_complete and attested),
            "local_dependencies": [item for item in checks if not item["portable"] or item["embedded_local_paths"]]}


def attest(root, reviewer, notes, checks):
    status = verify(root)
    if not status["production_evidence_complete"]:
        raise ValueError("文件清单或关键生产回执不完整，不能签收交付：" + "; ".join(status["evidence_issues"]))
    if (not reviewer.strip() or not notes.strip() or set(checks) != set(HANDOFF_CHECKS)
            or not all(checks.get(name) is True for name in HANDOFF_CHECKS)):
        raise ValueError("实际审核人须逐项检查并填写具体交付说明")
    data = {"task_id": status["task_id"], "manifest_sha256": manifest_sha256(root),
            "reviewer": reviewer.strip(), "notes": notes.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(), **checks,
            "attestation": "由实际审核人填写；程序不能独立证明素材内容或平台画面"}
    with attestation_path(root).open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return verify(root)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    first = sub.add_parser("init"); first.add_argument("--out", required=True); first.add_argument("--task-id", required=True)
    record = sub.add_parser("add"); record.add_argument("--run", required=True); record.add_argument("--role", required=True, choices=ROLES)
    record.add_argument("--file", required=True); record.add_argument("--copy", action="store_true"); record.add_argument("--label", default="")
    check = sub.add_parser("verify"); check.add_argument("--run", required=True)
    done = sub.add_parser("attest"); done.add_argument("--run", required=True)
    done.add_argument("--reviewer", required=True); done.add_argument("--notes", required=True)
    for flag in ("sources-and-translation-checked", "clips-and-video-played",
                 "subtitles-and-qc-checked", "publication-and-cover-checked",
                 "youtube-private-video-and-cover-seen"):
        done.add_argument("--" + flag, action="store_true")
    args = p.parse_args()
    if args.command == "init": result = init(args.out, args.task_id)
    elif args.command == "add": result = add(args.run, args.role, args.file, args.copy, args.label)
    elif args.command == "attest":
        checks = {name: getattr(args, name) for name in HANDOFF_CHECKS}
        result = attest(args.run, args.reviewer, args.notes, checks)
    else: result = verify(args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
