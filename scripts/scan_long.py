#!/usr/bin/env python3
"""Resume bounded scans of long videos and report actual covered intervals."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from select_candidates import scan, merge
from slice import probe_video


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def intervals(start, end, segment_seconds, minimum, overlap=0):
    spans = []
    cursor = start
    while cursor < end - 0.001:
        stop = min(cursor + segment_seconds + overlap, end)
        if end - stop < minimum and stop < end:
            stop = end
        spans.append((round(cursor, 3), round(stop - cursor, 3)))
        if stop == end:
            break
        cursor += segment_seconds
    return spans


def run(source, rules, out, scan_start=0, scan_seconds=None, segment_seconds=600,
        max_candidates=0, scanner=scan, prober=probe_video):
    source, rules, out = Path(source).expanduser().resolve(), Path(rules).resolve(), Path(out)
    if not source.is_file() or not rules.is_file():
        raise FileNotFoundError("源视频或规则不存在")
    duration = prober(source)[0]
    start = float(scan_start)
    end = min(duration, start + float(scan_seconds)) if scan_seconds is not None else duration
    if start < 0 or start >= duration or end - start < 30 or segment_seconds < 30 or max_candidates < 0:
        raise ValueError("扫描范围或分段参数无效")
    out.mkdir(parents=True, exist_ok=True)
    source_info = {"path": str(source), "size": source.stat().st_size,
                   "mtime_ns": source.stat().st_mtime_ns, "rules_sha256": file_hash(rules)}
    overlap = float(json.loads(rules.read_text(encoding="utf-8")).get("max_seconds", 45))
    scan_parameters = {"algorithm_version": 2, "overlap_seconds": overlap,"segment_seconds": float(segment_seconds), "max_candidates": int(max_candidates)}
    manifest_path = out / "scan-manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (previous.get("source_info") != source_info or previous.get("requested_range") != [start, end]
                or previous.get("scan_parameters") != scan_parameters):
            raise ValueError("源片、规则或扫描范围已变化；须使用新输出目录")
    else:
        manifest_path.write_text(json.dumps({"source_info": source_info, "requested_range": [start, end],
                                            "scan_parameters": scan_parameters}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage, all_candidates, resumed = [], [], 0
    for index, (segment_start, length) in enumerate(intervals(start, end, segment_seconds, 30, overlap), 1):
        segment_dir = out / f"segment-{index:04d}"
        result_path = segment_dir / "candidates.json"
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if (result.get("source") != str(source) or result.get("scan_start") != segment_start
                    or abs(result.get("scan_seconds", 0) - length) > 0.01):
                raise ValueError("已有分段结果与本次扫描不符；须使用新输出目录")
            resumed += 1
        elif segment_dir.exists():
            raise ValueError("分段目录不完整；请人工核查后移动残留目录，再续跑：" + str(segment_dir))
        else:
            result = scanner(SimpleNamespace(input=str(source), rules=str(rules), out=str(segment_dir),
                                             scan_start=segment_start, scan_seconds=length,
                                             max_candidates=max_candidates))
        coverage.append([segment_start, round(segment_start + length, 3)])
        for candidate in result.get("candidates", []):
            candidate = dict(candidate)
            candidate["segment"] = index
            if not any(abs(candidate["start"] - old["start"]) < 1 and abs(candidate["end"] - old["end"]) < 1
                       for old in all_candidates):
                all_candidates.append(candidate)
    for number, candidate in enumerate(all_candidates, 1):
        candidate["segment_candidate_id"] = candidate["id"]
        candidate["id"] = number
    covered = merge(coverage)
    report = {"source": str(source), "rules": str(rules), "action_review_required": True, "source_info": source_info, "scan_parameters": scan_parameters,
              "source_duration": duration, "requested_range": [start, end],
              "covered_intervals": coverage, "coverage_seconds": round(sum(b-a for a, b in covered), 3),
              "full_source_covered": len(covered) == 1 and covered[0][0] == 0 and abs(covered[0][1] - duration) < 0.01,
              "segments_resumed": resumed, "candidates": all_candidates,
              "note": "覆盖只表示机械扫描过该时段；候选仍需 Agent 视觉检查，未证明整片均有合格画面"}
    (out / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--scan-start", type=float, default=0)
    p.add_argument("--scan-seconds", type=float)
    p.add_argument("--segment-seconds", type=float, default=600)
    p.add_argument("--max-candidates", type=int, default=0)
    args = p.parse_args()
    result = run(args.input, args.rules, args.out, args.scan_start, args.scan_seconds,
                 args.segment_seconds, args.max_candidates)
    print(json.dumps({"covered_intervals": result["covered_intervals"],
                      "candidates": len(result["candidates"]), "full_source_covered": result["full_source_covered"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
