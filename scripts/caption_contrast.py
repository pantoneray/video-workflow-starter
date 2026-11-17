"""Sample actual caption-band luminance across video; recommendation, not QC approval."""
import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess


def recommend(video, y=1360, samples=9, ffmpeg="ffmpeg"):
    if not 1300 <= y <= 1560 or not 3 <= samples <= 30:
        raise ValueError("unsupported caption position or sample count")
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(video)],
                                    capture_output=True, text=True, check=True, timeout=30).stdout)
    duration = float(info["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid duration")
    rows = []
    for i in range(samples):
        time = duration * (i + .5) / samples
        filters = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,crop=800:180:140:{int(y)-90},scale=80:18,format=gray"
        frame = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-ss", str(time), "-i", str(video),
                                "-frames:v", "1", "-vf", filters, "-f", "rawvideo", "pipe:1"],
                               capture_output=True, check=True, timeout=30).stdout
        if len(frame) != 80 * 18:
            raise ValueError("caption sample decode failed")
        values = sorted(frame)
        rows.append({"time": round(time, 3), "median_luma": statistics.median(values),
                     "p90_luma": values[int(.9 * len(values))], "spread": values[int(.9*len(values))]-values[int(.1*len(values))]})
    variable = max(x["median_luma"] for x in rows) - min(x["median_luma"] for x in rows) > 55
    bright = any(x["p90_luma"] > 180 for x in rows)
    textured = any(x["spread"] > 100 for x in rows)
    return {"state": "recommendation_visual_review_required", "samples": rows, "caption_y": y,
            "background_changes": variable, "bright_or_textured": bright or textured,
            "recommended_templates": ["B", "C"] if bright or textured or variable else ["D", "B"],
            "contrast": "box" if variable or textured else "outline" if bright else None,
            "scope": "sampled subtitle background after centered portrait crop; no face detection or full-frame guarantee",
            "review_required": ["all scene changes", "face avoidance", "actual rendered phone-size readability", "platform UI overlap"],
            "thresholds": "heuristic candidates, not perceptual accessibility certification"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", required=True); p.add_argument("--out", required=True)
    p.add_argument("--y", type=int, default=1360); p.add_argument("--samples", type=int, default=9)
    a = p.parse_args()
    report = recommend(a.video, a.y, a.samples)
    with Path(a.out).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
