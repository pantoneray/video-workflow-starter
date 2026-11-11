#!/usr/bin/env python3
"""Measure aligned-cue pacing and require human playback checks after HeyGen."""
import argparse
import json
import math
from datetime import datetime
from pathlib import Path

from check_output import inspect, sha256
from speech_plan import effective_count
from subtitle_tools import full_text, normalized, parse_srt, read_text

MANUAL = ("voice_match", "lip_sync", "audio_video_sync", "speech_natural", "start_end_ok")


def prepare(video, aligned_srt, target_text, profile_path, out):
    video, aligned_srt, target_text, profile_path, out = map(Path, (video, aligned_srt, target_text, profile_path, out))
    if out.exists():
        raise FileExistsError(out)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("approved") is not True:
        raise ValueError("语种语速配置尚未听审批准")
    target_rate = float(profile["target_effective_cpm"])
    allowed = float(profile["max_cue_rate_deviation_ratio"])
    if not math.isfinite(target_rate) or target_rate <= 0 or not math.isfinite(allowed) or not 0 <= allowed <= 1:
        raise ValueError("须设置有效的目标语速和逐句偏差容差")
    video_qc = inspect(video)
    if video_qc["decode"] != "PASS" or not video_qc["audio"]:
        raise ValueError("成片须完整解码且包含音轨")
    cues = parse_srt(aligned_srt)
    if cues[-1].end / 1000 > video_qc["duration_s"] + .1:
        raise ValueError("最终字幕时间超出成片")
    if normalized(full_text(cues)) != normalized(read_text(target_text)):
        raise ValueError("最终字幕正文与审定目标文案不一致")
    measured = []
    for index, cue in enumerate(cues, 1):
        count = effective_count(cue.text)
        span = (cue.end - cue.start) / 1000
        rate = count / span * 60
        deviation = rate / target_rate - 1
        measured.append({"cue": index, "start_ms": cue.start, "end_ms": cue.end,
                         "effective_characters": count, "cue_effective_cpm": round(rate, 2),
                         "deviation_ratio": round(deviation, 3),
                         "rate_flag": "review" if abs(deviation) > allowed else "within_configured_range"})
    report = {"status": "pending_human_playback", "video": str(video.resolve()), "video_sha256": sha256(video),
              "aligned_srt": str(aligned_srt.resolve()), "aligned_srt_sha256": sha256(aligned_srt),
              "target_text": str(target_text.resolve()), "target_text_sha256": sha256(target_text),
              "speed_profile": str(profile_path.resolve()), "speed_profile_sha256": sha256(profile_path),
              "target_effective_cpm": target_rate, "max_cue_rate_deviation_ratio": allowed,
              "cue_measurements": measured, "flagged_cues": [x["cue"] for x in measured if x["rate_flag"] == "review"],
              "measurement_note": "按对齐字幕的显示时长估算，不能证明实际发音速度；逐句听审为准",
              "manual_review": {"reviewer": None, "reviewed_at": None, **{name: None for name in MANUAL},
                                "rate_exception_reason": None}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify(report_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    for path_key, hash_key in (("video", "video_sha256"), ("aligned_srt", "aligned_srt_sha256"),
                               ("target_text", "target_text_sha256"), ("speed_profile", "speed_profile_sha256")):
        path = Path(report[path_key])
        if not path.is_file() or sha256(path) != report[hash_key]:
            raise ValueError("成片质检输入已变化或缺失：" + path_key)
    review = report.get("manual_review") or {}
    try:
        stamp = datetime.fromisoformat(str(review.get("reviewed_at")))
        if stamp.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise ValueError("人工听审时间须为带时区的 ISO 日期") from exc
    if not review.get("reviewer") or any(review.get(name) is not True for name in MANUAL):
        raise ValueError("缺实际审核人或口型/音画/语速/起止逐项通过记录")
    if report.get("flagged_cues") and not review.get("rate_exception_reason"):
        raise ValueError("逐句语速异常须听审并填写具体处理或例外理由")
    return {"status": "human_playback_attested", "reviewer": review["reviewer"],
            "flagged_cues": report.get("flagged_cues", []), "video_sha256": report["video_sha256"]}


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--video", required=True); a.add_argument("--aligned-srt", required=True)
    a.add_argument("--target-text", required=True); a.add_argument("--profile", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("verify"); a.add_argument("--report", required=True)
    args = p.parse_args()
    result = prepare(args.video, args.aligned_srt, args.target_text, args.profile, args.out) if args.command == "prepare" else verify(args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
