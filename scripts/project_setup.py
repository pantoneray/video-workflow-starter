#!/usr/bin/env python3
"""Keep private paths in a user's project, never in the distributed skill."""
import argparse
import json
import os
from pathlib import Path

from config_paths import resolve_path

MEMORY = "VIDEO-WORKFLOW-MEMORY.md"
MARKER = "<!-- video-workflow-starter: read VIDEO-WORKFLOW-MEMORY.md before video tasks -->"
BEGIN = "<!-- video-workflow-starter: config begin -->"
END = "<!-- video-workflow-starter: config end -->"
GROUPS = ("life_corpus", "deep_corpus", "glossary", "video_sources", "output")
OPTIONAL = ("speed_samples", "subtitle_rules", "brand_assets", "cover_references", "youtube_config")
FORMATS = {"life_corpus": {".md", ".markdown", ".txt", ".pdf"},
           "deep_corpus": {".md", ".markdown", ".txt", ".pdf"},
           "glossary": {".csv", ".md", ".txt", ".json"},
           "video_sources": {".mp4", ".mov", ".mkv", ".m4v"},
           "speed_samples": {".wav", ".mp3", ".m4a", ".txt", ".md"},
           "subtitle_rules": {".md", ".txt", ".json"},
           "brand_assets": {".png", ".jpg", ".jpeg", ".svg"},
           "cover_references": {".png", ".jpg", ".jpeg", ".md", ".pdf"},
           "youtube_config": {".json"}}


def check(config, base_dir=None):
    paths = config.get("paths", {})
    report = {}
    for key in GROUPS + OPTIONAL:
        values = paths.get(key)
        if isinstance(values, str):
            values = [values]
        if not values:
            report[key] = {"status": "not_configured"}
            continue
        checked = []
        for value in values:
            p = resolve_path(value, base_dir)
            exists = p.exists()
            readable = exists and os.access(p, os.R_OK)
            format_ok = p.is_dir() if key == "output" else (p.is_dir() or p.suffix.lower() in FORMATS.get(key, set()))
            checked.append({"path": str(p), "exists": exists, "readable": readable, "format_ok": format_ok})
        report[key] = {"status": "ready" if all(v["readable"] and v["format_ok"] for v in checked) else "unavailable", "items": checked}
    return report


def memory_block(config_path, report):
    lines = [BEGIN, "## 路径", ""]
    for key in GROUPS + OPTIONAL:
        entry = report[key]
        lines.append(f"### {key} — {entry['status']}")
        for item in entry.get("items", []):
            lines.append(f"- `{item['path']}`")
        lines.append("")
    lines.extend(["## 使用规则", "", "选文与画面准备并行；文案出处和画面来源分别记录。译审、人审与付费授权按各任务独立记录。", "", "私密配置文件：`" + str(Path(config_path).expanduser().resolve()) + "`", END])
    return "\n".join(lines)


def initialize(config_path, project_root, sync=False):
    project = Path(project_root).expanduser().resolve()
    if not project.is_dir():
        raise ValueError("项目目录不存在")
    config = json.loads(Path(config_path).expanduser().read_text(encoding="utf-8"))
    report = check(config, Path(config_path).expanduser().resolve().parent)
    memory = project / MEMORY
    block = memory_block(config_path, report)
    if sync:
        if not memory.is_file():
            raise FileNotFoundError("项目记忆不存在；先运行 init")
        existing = memory.read_text(encoding="utf-8")
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError("项目记忆缺受管配置区；请人工核查，不能覆盖")
        start = existing.index(BEGIN)
        stop = existing.index(END) + len(END)
        memory.write_text(existing[:start] + block + existing[stop:], encoding="utf-8")
        return {"memory": str(memory), "paths": report, "updated": True}
    if memory.exists():
        raise FileExistsError("项目记忆已存在；请先核对，避免覆盖：" + str(memory))
    memory.write_text("# 视频工作流项目配置\n\n此文件仅留在本项目，不要随 Skill 分发。路径失效时只暂停依赖该路径的步骤。\n\n" + block + "\n", encoding="utf-8")
    agents = project / "AGENTS.md"
    if agents.exists():
        body = agents.read_text(encoding="utf-8")
        if MARKER not in body:
            with agents.open("a", encoding="utf-8") as out:
                out.write("\n" + MARKER + "\n视频任务先读本项目的 `VIDEO-WORKFLOW-MEMORY.md`；按需检查私密配置的路径。\n")
    else:
        agents.write_text("# 项目规则\n\n" + MARKER + "\n视频任务先读本项目的 `VIDEO-WORKFLOW-MEMORY.md`；按需检查私密配置的路径。\n", encoding="utf-8")
    return {"memory": str(memory), "agents": str(agents), "paths": report}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "init", "sync"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--project-root")
    args = parser.parse_args()
    config = json.loads(Path(args.config).expanduser().read_text(encoding="utf-8"))
    if args.command in ("init", "sync"):
        if not args.project_root:
            parser.error("init/sync 需要 --project-root")
        result = initialize(args.config, args.project_root, sync=args.command == "sync")
    else:
        result = check(config, Path(args.config).expanduser().resolve().parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
