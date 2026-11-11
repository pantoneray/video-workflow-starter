#!/usr/bin/env python3
"""Collect sentence/semantic-segment versions into a local human review packet."""
import argparse
import difflib
import json
from pathlib import Path

from translation_review import load, version_digest


def render(entries, base):
    lines = ["# 译审包", "", "每条均须明确给出通过、修改、拒绝或暂缓；未评价即待确认。模型意见不构成人工批准。", ""]
    for index, entry in enumerate(entries, 1):
        version = load(base / entry["version"])
        decision = load(base / entry["decision"]) if entry.get("decision") else None
        valid = (decision and decision.get("version") == version.get("version")
                 and decision.get("translation_sha256") == version.get("translation_sha256")
                 and decision.get("version_sha256") == version_digest(version))
        status = decision["decision"] if valid else "pending"
        source = version["source"]
        previous = load(base / entry["previous"]) if entry.get("previous") else None
        difference = "" if not previous else "\n".join(difflib.ndiff(previous["translation"].splitlines(),
                                                                    version["translation"].splitlines()))
        lines += [f"## {index}. 版本 {version['version']} — {status}", "",
                  f"- 出处：`{source.get('file', '未知')}`，{source.get('section', '')} {source.get('locator', '未定位')}",
                  f"- 资料版本：`{source.get('version', '未提供')}`", "",
                  "**中文原文**", "", source["original_exact"], "",
                  "**目标语译稿**", "", version["translation"], "",
                  "**独立译文（仅看原文）**", "", version.get("independent_translation", "旧版未记录"), "",
                  "**本版盲回译**", "", version["blind_backtranslation"], "",
                  "**术语参考**", "", ", ".join(map(str, version.get("glossary", []))) or "无", "",
                  "**独立复核与疑点**", "", version["independent_review"], "",
                  "**上一版意见回应**", "", json.dumps(version.get("feedback_response"), ensure_ascii=False) if version.get("feedback_response") else "无", "",
                  "**前后译稿差异**", "", "```diff", difference or "无上一版", "```", "",
                  "**人工逐条意见**", "", decision.get("feedback", "待评价") if valid else "待评价", "",
                  f"审核人：{decision.get('reviewer', '待确认') if valid else '待确认'}", ""]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--items", required=True, help="JSON 列表，每项含 version、可选 previous/decision 路径")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    manifest = Path(args.items).resolve()
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        p.error("items 须是非空列表")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        f.write(render(entries, manifest.parent))
    print(json.dumps({"review_packet": str(out.resolve()), "items": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
