#!/usr/bin/env python3
"""One command entry for the portable workflow's independently usable stages."""
import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPTIONAL_VENV = {"source", "heygen-api", "youtube", "package", "captions", "cover", "publication-review", "delivery"}
STAGES = {
    "batch-clips": "batch_clips.py",
    "env": "check_env.py", "guide": "guide.py", "project": "project_setup.py", "source": "source_search.py",
    "review": "translation_review.py", "review-packet": "review_bundle.py", "scan": "select_candidates.py", "scan-long": "scan_long.py",
    "slice": "slice.py", "qc": "check_output.py", "upload-video": "prepare_upload_video.py", "post-heygen-qc": "post_heygen_qc.py", "speech": "speech_plan.py",
    "subtitle": "subtitle_tools.py", "paid-authorization": "paid_authorization.py", "heygen-web": "heygen_web.py",
    "heygen-api": "heygen_portable.py", "youtube": "youtube_portable.py",
    "package": "package_video.py", "cover": "cover.py", "metadata": "publication_assets.py", "publication-review": "publication_review.py", "delivery": "delivery.py",
    "align": "../tools/faithful-audio-align/scripts/align.py",
    "captions": "caption_templates.py",
    "frame-check": "../tools/production-packaging/select_template.py",
    "silent-mouth": "../tools/production-packaging/silent_mouth.py",
}


def environment_name():
    return ".venv-wsl" if sys.platform == "linux" and "microsoft" in platform.release().casefold() else ".venv"


def interpreter(stage):
    if stage == "align":
        name = ".venv-align-wsl" if environment_name() == ".venv-wsl" else ".venv-align"
        python = ROOT / name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if not python.is_file():
            raise FileNotFoundError("先运行 install align 安装可选本地强制对齐依赖")
        return str(python)
    if stage in OPTIONAL_VENV:
        python = ROOT / environment_name() / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if python.is_file():
            return str(python)
    return sys.executable


def main():
    p = argparse.ArgumentParser(description="视频工作流统一脚本入口；阶段详情用 python workflow.py <阶段> --help")
    p.add_argument("stage", nargs="?", choices=STAGES)
    if len(sys.argv) >= 2 and sys.argv[1] in STAGES:
        stage, rest = sys.argv[1], sys.argv[2:]
    else:
        args = p.parse_args()
        if not args.stage:
            p.print_help()
            return 0
        stage, rest = args.stage, []
    try:
        python = interpreter(stage)
    except FileNotFoundError as exc:
        if "--help" in rest or "-h" in rest:
            python = sys.executable
        else:
            p.error(str(exc))
    return subprocess.call([python, str(ROOT / "scripts" / STAGES[stage]), *rest])


if __name__ == "__main__":
    raise SystemExit(main())
