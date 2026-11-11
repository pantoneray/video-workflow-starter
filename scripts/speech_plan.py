#!/usr/bin/env python3
"""Calibrate effective characters/minute and make a pre-HeyGen timing draft.

Each non-empty line of the approved text is a human-chosen sentence/cue.
The resulting SRT is an estimate, never an alignment to generated audio.
"""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def effective_count(text):
    return sum(ch.isalnum() for ch in text)


def read_lines(path):
    lines = [line.strip() for line in Path(path).read_text(encoding="utf-8-sig").splitlines()]
    lines = [line for line in lines if line]
    if not lines or any(effective_count(line) == 0 for line in lines):
        raise ValueError("文案须按自然断句逐行填写，每行含有效字符")
    return lines


def duration(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                            capture_output=True, text=True, timeout=30, check=True)
    value = float(result.stdout.strip())
    if not math.isfinite(value) or value <= 0:
        raise ValueError("视频/音频时长无效")
    return value


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(value)


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def calibrate(text_path, audio_path, speech_seconds, locale, output):
    lines = read_lines(text_path)
    full = duration(audio_path)
    span = float(speech_seconds) if speech_seconds is not None else full
    if not math.isfinite(span) or not 0 < span <= full + 0.1:
        raise ValueError("speech-seconds 须为有效讲话时长且不超过音频时长")
    count = effective_count("".join(lines))
    result = {"locale": locale, "counting_rule": "unicode_alphanumeric_excluding_spaces_and_punctuation",
              "effective_characters": count, "sample_audio_seconds": round(full, 3),
              "sample_speech_seconds": round(span, 3),
              "target_effective_cpm": round(count / span * 60, 2),
              "sample_text_sha256": sha(text_path), "sample_audio_sha256": sha(audio_path),
              "approved": False, "pause_seconds_between_cues": None,
              "max_duration_difference_seconds": None,
              "max_cue_rate_deviation_ratio": None,
              "note": "候选校准值；听审认可后由本语种负责人设 approved=true、停顿、时长容差和逐句语速偏差容差"}
    write_new(output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def prepare(text_path, clip_path, profile_path, out):
    lines = read_lines(text_path)
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if profile.get("approved") is not True:
        raise ValueError("语种参考语速配置尚未经用户确认")
    if profile.get("counting_rule") != "unicode_alphanumeric_excluding_spaces_and_punctuation":
        raise ValueError("未知有效字符计数规则")
    rate = float(profile["target_effective_cpm"])
    pause = float(profile["pause_seconds_between_cues"])
    tolerance = float(profile["max_duration_difference_seconds"])
    if not all(math.isfinite(x) for x in (rate, pause, tolerance)) or rate <= 0 or pause < 0 or tolerance < 0:
        raise ValueError("语速、停顿或时长容差无效")
    clip_seconds = duration(clip_path)
    counts = [effective_count(line) for line in lines]
    expected_speech = sum(counts) / rate * 60
    expected_total = expected_speech + pause * (len(lines) - 1)
    difference = round(expected_total - clip_seconds, 3)
    result = {"status": "ready_for_review" if abs(difference) <= tolerance else "needs_better_clip_or_text_review",
              "purpose": "estimated_pre_heygen_timeline_not_final_audio_alignment",
              "locale": profile.get("locale"), "effective_characters": sum(counts),
              "target_effective_cpm": rate, "estimated_speech_seconds": round(expected_speech, 3),
              "estimated_total_seconds": round(expected_total, 3), "clip_seconds": round(clip_seconds, 3),
              "difference_seconds": difference, "tolerance_seconds": tolerance,
              "cue_count": len(lines), "text_sha256": sha(text_path), "clip_sha256": sha(clip_path),
              "profile_sha256": sha(profile_path)}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "preflight.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if result["status"] != "ready_for_review":
        return result
    cursor = 0.0
    cues = []
    for i, (line, count) in enumerate(zip(lines, counts), 1):
        end = cursor + count / rate * 60
        cues.append(f"{i}\n{timestamp(cursor)} --> {timestamp(end)}\n{line}\n")
        cursor = end + pause
    write_new(out / "planned-not-final.srt", "\n".join(cues) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    c = sub.add_parser("calibrate"); c.add_argument("--text", required=True); c.add_argument("--audio", required=True); c.add_argument("--speech-seconds", type=float); c.add_argument("--locale", required=True); c.add_argument("--out", required=True)
    c = sub.add_parser("prepare"); c.add_argument("--text", required=True); c.add_argument("--clip", required=True); c.add_argument("--profile", required=True); c.add_argument("--out", required=True)
    a = p.parse_args()
    try:
        result = calibrate(a.text, a.audio, a.speech_seconds, a.locale, a.out) if a.action == "calibrate" else prepare(a.text, a.clip, a.profile, a.out)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        p.exit(2, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status", "ready_for_review") == "ready_for_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
