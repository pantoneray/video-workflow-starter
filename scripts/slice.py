#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slice.py — 源片 + cuts.json → 片段目录 + manifest.json

用法：
  python3 scripts/slice.py --input <源片.mp4> --cuts <cuts.json> --out <目录> [--dry-run]

cuts.json 结构：
  [{"start": 0.0, "end": 4.872, "label": "sample"}]

manifest.json 每段含：index / label / note / start / end / file / duration / resolution / sha256。
切片用重编码（libx264 + AAC），保证入出点精确（关键帧抽粗候选以外的最终入库口径）。
"""
import argparse
import hashlib
import json
import subprocess
import math
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_video(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 失败：{r.stderr[:200]}")
    data = json.loads(r.stdout)
    s = next(x for x in data["streams"] if x["codec_type"] == "video")
    return float(data["format"]["duration"]), int(s["width"]), int(s["height"])


def safe_name(label):
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(label)).strip("-") or "seg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="可选：本机 JSON 配置")
    ap.add_argument("--input")
    ap.add_argument("--cuts", required=True)
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    config = json.loads(Path(a.config).read_text(encoding="utf-8")) if a.config else {}
    a.input = a.input or config.get("paths", {}).get("input")
    a.out = a.out or config.get("paths", {}).get("output")
    if not a.input or not a.out:
        ap.error("请用 --input/--out 或配置文件 paths.input/paths.output 指定路径")
    source = Path(a.input).expanduser().resolve()
    if not source.is_file():
        ap.error("输入视频不存在")
    source_duration, _, _ = probe_video(source)
    cuts = json.loads(Path(a.cuts).read_text(encoding="utf-8"))
    if not isinstance(cuts, list) or not cuts:
        raise SystemExit("cuts.json 要是一个非空数组")
    for i, cut in enumerate(cuts, 1):
        try:
            start, end = float(cut["start"]), float(cut["end"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"第 {i} 段缺少有效 start/end")
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= source_duration + 0.05):
            raise SystemExit(f"第 {i} 段超出源片时长或时间无效")

    out = Path(a.out)
    segdir = out / "segments"
    if out.resolve() == source or source in out.resolve().parents:
        raise SystemExit("输出目录不能是源视频或其上级目录")

    manifest = {
        "source": str(source),
        "cuts_file": str(Path(a.cuts).resolve()),
        "segments": [],
    }
    for i, c in enumerate(cuts, 1):
        seg = segdir / f"seg-{i:02d}-{safe_name(c.get('label'))}.mp4"
        manifest["segments"].append({
            "index": i,
            "label": c.get("label", f"seg-{i}"),
            "note": c.get("note", ""),
            "start": float(c["start"]),
            "end": float(c["end"]),
            "file": str(seg),
        })

    if a.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    if (out / "manifest.json").exists() or any(Path(s["file"]).exists() for s in manifest["segments"]):
        raise SystemExit("输出已存在；请使用新的运行目录，避免覆盖历史")
    segdir.mkdir(parents=True, exist_ok=True)

    for s in manifest["segments"]:
        cmd = [
            "ffmpeg", "-n",
            "-ss", str(s["start"]), "-to", str(s["end"]),
            "-i", str(source),
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            s["file"],
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise RuntimeError(f"切片 {s['label']} 失败：{r.stderr[-300:]}")
        dur, w, h = probe_video(s["file"])
        s["duration"] = round(dur, 3)
        s["resolution"] = f"{w}x{h}"
        s["sha256"] = sha256(s["file"])

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
