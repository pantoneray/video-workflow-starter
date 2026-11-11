#!/usr/bin/env python3
"""Read-only stage guide for a user's local video project and delivery run."""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from delivery import ROLES, verify as verify_delivery
from project_setup import check as check_paths

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("prepare", "source", "clips", "translation", "heygen", "finish", "youtube", "delivery")
DEPENDENCIES = {"prepare": [], "source": [], "clips": [], "translation": [],
                "heygen": ["--with-heygen"], "finish": ["--with-packaging"],
                "youtube": ["--with-youtube", "--with-packaging"],
                "delivery": ["--with-packaging"]}
GUIDANCE = {
    "prepare": {"needs": "Python、FFmpeg/FFprobe，以及本人项目中可读的资料、术语表、视频与输出目录",
                "next": "复制 config.example.json 到包外项目，填本人路径；运行 workflow.py project check/init，项目记忆会保留这些路径。",
                "human": "确认资料与素材使用权；扫描 PDF 先 OCR。"},
    "source": {"needs": "已配置的生活应用或深入法义语料；主题示例可在项目内修改",
               "next": "用 workflow.py source 在指定主题和语料范围生成带出处候选；核对原文、上下文、章节与断章风险。",
               "human": "选文须人工确认；深入法义须专业审核。"},
    "clips": {"needs": "已配置的视频素材目录与本机 FFmpeg；可与选文同时进行",
              "next": "用 workflow.py scan 或 scan-long 默认扫描全视频，运行 scan review 连续检查候选及特殊手势/低头，scan choose 一次选多条不重叠候选，再运行 slice 和 qc；切片写新目录。",
              "human": "初期亲自播放检查起止、动作、卡顿与跳切。"},
    "translation": {"needs": "已核对的原文出处、目标语种、模型配置和本机 GEMINI_API_KEY",
                    "next": "用 workflow.py review create/revise 并传 --project-config <本人配置>，只取当前原文命中的目标语术语，分别做初译、独立翻译、盲回译、对照复核；生成审稿包并由实际审核人逐版决定。返修需重新传配置。",
                    "human": "模型调用会发出原文或译稿；人工批准须绑定当前整版。"},
    "heygen": {"needs": "已批准目标文案、匹配切片、用户确认的参考语速 profile（直接提供、平均值估算或音频测算）、HeyGen CLI OAuth 本人账号",
               "next": "先做 speech 预检，再上传视频并创建 Proofread 草稿；上传批准 Output SRT，网页试听校对，另行批准最终生成和下载。命令见 INTEGRATIONS.md。",
               "human": "上传前本人核对账号、模式、时长与费用；创建和生成各需单次授权，网页审核本人完成。"},
    "finish": {"needs": "HeyGen 成片、按实际音频听审的最终 SRT、本机字体与可选品牌素材、Pillow",
               "next": "先运行 post-heygen-qc；再运行 package、cover、metadata 与 publication-review。",
               "human": "播放成片核对语速、口型、字幕、封面及标题简介 tags。"},
    "youtube": {"needs": "批准的最终成片与封面、发布审核回执、本人 GCP Desktop OAuth 和频道 ID",
                "next": "先 youtube auth/verify，再 upload-private、wait-processing、set-thumbnail；保存回执并在 Studio 查看实际显示。",
                "human": "仅私密上传；公开发布另行授权。跨账号的旧 OAuth 与授权不能沿用。"},
    "delivery": {"needs": "十类产物与回执，及实际审核人的最终签收",
                 "next": "用 workflow.py delivery add 登记产物，verify 查看 evidence_issues；证据完整后由本人运行 attest。",
                 "human": "亲自核对源文、成片和 YouTube Studio 私密视频及封面；Agent 不代签。"},
}


def optional_python():
    name = ".venv-wsl" if sys.platform == "linux" and "microsoft" in platform.release().casefold() else ".venv"
    candidate = ROOT / name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def environment(stage, runner=None):
    command = [optional_python(), str(ROOT / "scripts" / "check_env.py"), *DEPENDENCIES[stage]]
    run = runner or subprocess.run
    try:
        result = run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return {"scope": "local_dependencies_only", "status": "missing_dependency",
                "detail": "本机依赖检查未完成；请单独运行 workflow.py env 查看"}
    line = result.stdout.splitlines()[0] if result.stdout else "环境检查未返回结果"
    return {"scope": "local_dependencies_only", "status": "ready" if result.returncode == 0 else "missing_dependency",
            "detail": line}


def next_stages(missing):
    missing = set(missing)
    parallel = [stage for role, stage in (("source", "source"), ("clips", "clips")) if role in missing]
    if parallel:
        return parallel
    for roles, stage in ((("translation",), "translation"),
                         (("subtitles", "heygen"), "heygen"),
                         (("qc", "packaging", "cover", "metadata"), "finish"),
                         (("youtube",), "youtube")):
        if any(role in missing for role in roles):
            return [stage]
    return ["delivery"]


def path_blockers(stage, report):
    if report is None:
        return ["请提供 --config 指向本人项目的包外配置"]
    blockers = []
    if report.get("output") != "ready":
        blockers.append("output")
    if stage == "source" and not any(report.get(name) == "ready" for name in ("life_corpus", "deep_corpus")):
        blockers.append("life_corpus 或 deep_corpus")
    if stage == "clips" and report.get("video_sources") != "ready":
        blockers.append("video_sources")
    if stage == "translation" and report.get("glossary") != "ready":
        blockers.append("glossary")
    return blockers


def plan(config=None, run=None, stage=None, environment_runner=None):
    config_report = None
    if config:
        data = json.loads(Path(config).expanduser().read_text(encoding="utf-8"))
        config_report = {key: item["status"] for key, item in
                         check_paths(data, Path(config).expanduser().resolve().parent).items()}
    delivery_report = verify_delivery(run) if run else None
    if stage:
        selected = [stage]
    elif config_report is None or config_report.get("output") != "ready":
        selected = ["prepare"]
    elif delivery_report is None:
        selected = ["source", "clips"]
    else:
        selected = next_stages(delivery_report["missing_roles"])
    stages = []
    for name in selected:
        item = {"stage": name, **GUIDANCE[name], "environment": environment(name, environment_runner)}
        item["path_blockers"] = path_blockers(name, config_report)
        if name == "translation": item["model_key_configured"] = bool(os.environ.get("GEMINI_API_KEY"))
        if name == "heygen":
            item["heygen_api_key_overrides_oauth"] = bool(os.environ.get("HEYGEN_API_KEY"))
            item["account_and_paid_permission"] = "not_checked"
        if name == "youtube": item["google_account_channel_and_upload_permission"] = "not_checked"
        stages.append(item)
    return {"status": "read_only_guidance", "stages": stages,
            "project_paths": config_report, "delivery": delivery_report,
            "external_or_paid_action_taken": False,
            "details": "README.md 为主指南；平台命令和账号边界见 INTEGRATIONS.md；本命令不登录、不上传、不生成。"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", help="本人项目的包外 video-config.json")
    p.add_argument("--run", help="已有的交付目录；只读核对缺失角色和证据")
    p.add_argument("--stage", choices=STAGES, help="查看指定阶段的条件和下一步")
    args = p.parse_args()
    print(json.dumps(plan(args.config, args.run, args.stage), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
