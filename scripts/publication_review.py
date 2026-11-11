#!/usr/bin/env python3
"""Bind human approval of metadata and an actual cover to the current reviewed text."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from check_output import inspect, sha256
from translation_review import load, verify_approval, version_digest, write_new


def checked_cover(path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("封面审核需要 Pillow；先运行 install packaging") from exc
    if not path:
        raise ValueError("缺少批准的封面图")
    image = Path(path)
    if not image.is_file() or image.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise ValueError("须提供实际 JPEG/PNG 封面图")
    try:
        with Image.open(image) as opened:
            if opened.format not in ("JPEG", "PNG") or min(opened.size) < 320:
                raise ValueError("封面格式或尺寸不足；请检查实际图像")
            opened.verify()
    except OSError as exc:
        raise ValueError("封面图无法完整解码") from exc
    return image


def candidate_binding(candidate, version, approval):
    current = verify_approval(version, approval)
    if (candidate.get("status") != "pending_human_review"
            or candidate.get("version") != current["version"]
            or candidate.get("version_sha256") != current["version_sha256"]
            or candidate.get("translation_sha256") != current["translation_sha256"]):
        raise ValueError("发布资料候选与当前批准译稿不一致")
    if not all(isinstance(candidate.get(k), str) and candidate[k].strip()
               for k in ("title", "description", "cover_text")):
        raise ValueError("标题、简介或封面文字缺失")
    if (not isinstance(candidate.get("tags"), list)
            or any(not isinstance(x, str) or not x.strip() for x in candidate["tags"])):
        raise ValueError("tags 格式无效")
    return current


def decide(candidate_path, version_path, approval_path, video_path, cover_path, reviewer, decision, feedback, out):
    candidate = load(candidate_path)
    current = candidate_binding(candidate, load(version_path), load(approval_path))
    if decision not in ("approve", "revise", "reject", "defer"):
        raise ValueError("发布资料决定须为 approve/revise/reject/defer")
    if not reviewer.strip() or not feedback.strip():
        raise ValueError("须由实际审核人填写姓名和具体意见")
    cover = checked_cover(cover_path) if cover_path else None
    if decision == "approve" and cover is None:
        raise ValueError("批准发布资料前须检查实际封面图")
    video = Path(video_path) if video_path else None
    if decision == "approve" and (not video or not video.is_file()):
        raise ValueError("批准发布资料前须检查最终成片")
    video_qc = inspect(video) if video and video.is_file() else None
    if decision == "approve" and (video_qc["decode"] != "PASS" or not video_qc["video"] or not video_qc["audio"]):
        raise ValueError("最终成片须完整解码且有画面和声音")
    result = {"decision": decision, "reviewer": reviewer, "feedback": feedback,
              "reviewed_at": datetime.now(timezone.utc).isoformat(),
              "candidate_sha256": version_digest(candidate),
              "version_sha256": current["version_sha256"],
              "cover_file": str(cover.resolve()) if cover and cover.is_file() else None,
              "cover_sha256": sha256(cover) if cover and cover.is_file() else None,
              "video_file": str(video.resolve()) if video and video.is_file() else None,
              "video_sha256": video_qc["sha256"] if video_qc else None,
              "video_qc": video_qc if decision == "approve" else None,
              "attestation": "由实际审核人输入；程序不能独立证明身份或画面内容"}
    write_new(out, result)
    return result


def verify(candidate_path, decision_path, version_path, approval_path, cover_path=None, video_path=None):
    candidate = load(candidate_path)
    current = candidate_binding(candidate, load(version_path), load(approval_path))
    decision = load(decision_path)
    cover = checked_cover(cover_path or decision.get("cover_file"))
    video = Path(video_path or decision.get("video_file") or "")
    if (decision.get("decision") != "approve" or not decision.get("reviewer")
            or not decision.get("feedback") or decision.get("candidate_sha256") != version_digest(candidate)
            or decision.get("version_sha256") != current["version_sha256"]
            or not cover.is_file() or decision.get("cover_sha256") != sha256(cover)
            or not video.is_file() or decision.get("video_sha256") != sha256(video)
            or (decision.get("video_qc") or {}).get("decode") != "PASS"):
        raise ValueError("发布资料或封面没有与当前译稿匹配的人工批准")
    try:
        reviewed = datetime.fromisoformat(str(decision.get("reviewed_at")))
        if reviewed.tzinfo is None:
            raise ValueError("no timezone")
    except ValueError as exc:
        raise ValueError("发布资料审核时间须带时区") from exc
    return {"title": candidate["title"], "description": candidate["description"],
            "tags": candidate["tags"], "cover_text": candidate["cover_text"],
            "cover_file": str(cover.resolve()), "cover_sha256": decision["cover_sha256"],
            "video_file": str(video.resolve()), "video_sha256": decision["video_sha256"],
            "candidate_sha256": decision["candidate_sha256"],
            "reviewer": decision["reviewer"], "version_sha256": current["version_sha256"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("decide", "verify"):
        a = sub.add_parser(name)
        a.add_argument("--candidate", required=True); a.add_argument("--version", required=True)
        a.add_argument("--approval", required=True); a.add_argument("--cover")
        a.add_argument("--video")
        if name == "decide":
            a.add_argument("--reviewer", required=True); a.add_argument("--decision", required=True,
                           choices=("approve", "revise", "reject", "defer"))
            a.add_argument("--feedback", required=True); a.add_argument("--out", required=True)
        else:
            a.add_argument("--decision-file", required=True)
    a = p.parse_args()
    result = (decide(a.candidate, a.version, a.approval, a.video, a.cover, a.reviewer, a.decision, a.feedback, a.out)
              if a.command == "decide" else verify(a.candidate, a.decision_file, a.version, a.approval, a.cover, a.video))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
