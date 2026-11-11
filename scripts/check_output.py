#!/usr/bin/env python3
"""Offline technical QC for an existing video; adapted from project edit.py checks."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def run(args, timeout=120):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(path):
    probe = run(["ffprobe", "-v", "error", "-show_entries",
                 "format=duration,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
                 "-of", "json", str(path)], 30)
    if probe.returncode:
        raise RuntimeError(probe.stderr.strip() or "ffprobe failed")
    metadata = json.loads(probe.stdout)
    decode = run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], 3600)
    video = next((s for s in metadata["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in metadata["streams"] if s["codec_type"] == "audio"), None)
    return {"file": str(path.resolve()), "sha256": sha256(path),
            "duration_s": float(metadata["format"].get("duration") or 0),
            "video": video, "audio": audio,
            "decode": "PASS" if decode.returncode == 0 else "FAIL",
            "decode_error": decode.stderr[-500:] if decode.returncode else ""}


def main():
    parser = argparse.ArgumentParser(description="检查视频可解码、时长、流信息和 SHA256")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="可选 JSON 报告；已有文件拒绝覆盖")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error("输入文件不存在")
    if args.out and args.out.exists():
        parser.error("报告已存在；请使用新路径")
    result = inspect(args.input)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decode"] == "PASS" and result["video"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
