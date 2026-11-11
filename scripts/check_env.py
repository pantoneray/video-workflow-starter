#!/usr/bin/env python3
"""Portable prerequisite check. Optional integrations are inspected only on request."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def heygen_cli_contract(cli):
    checks = (
        (["video-translate", "proofreads", "create", "--request-schema"],
         ("video", "output_languages", "mode", "enable_video_stretching", "srt")),
        (["video-translate", "proofreads", "srt", "update", "example", "--request-schema"], ("srt",)),
        (["video-translate", "proofreads", "generate", "example", "--request-schema"], ("translate_audio_only",)),
    )
    for command, fields in checks:
        try:
            proc = subprocess.run([cli, *command], capture_output=True, text=True, timeout=20)
            schema = json.loads(proc.stdout) if proc.returncode == 0 else {}
            if not all(field in schema.get("properties", {}) for field in fields):
                return False
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return False
        if command[2] == "create":
            props = schema["properties"]
            if "precision" not in props["mode"].get("enum", []) or props["enable_video_stretching"].get("type") != "boolean":
                return False
    responses = (
        (["video-translate", "proofreads", "create", "--response-schema"], ("proofread_ids",)),
        (["video-translate", "proofreads", "srt", "get", "example", "--response-schema"], ("srt_url",)),
        (["video-translate", "proofreads", "generate", "example", "--response-schema"], ("video_translation_id",)),
        (["video-translate", "get", "example", "--response-schema"], ("status", "video_url")),
    )
    for command, fields in responses:
        try:
            proc = subprocess.run([cli, *command], capture_output=True, text=True, timeout=20)
            schema = json.loads(proc.stdout) if proc.returncode == 0 else {}
            data = schema.get("properties", {}).get("data", {}).get("properties", {})
            if not all(field in data for field in fields):
                return False
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return False
    for command in (("video-translate", "proofreads", "create", "--help"),
                    ("video-translate", "proofreads", "generate", "example", "--help"),
                    ("asset", "create", "--help")):
        try:
            proc = subprocess.run([cli, *command], capture_output=True, text=True, timeout=15)
            if proc.returncode or "--idempotency-key" not in proc.stdout + proc.stderr:
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--with-heygen", action="store_true", help="检查网页校对路线所需的 HeyGen CLI")
    p.add_argument("--with-heygen-cli", action="store_true")
    p.add_argument("--with-heygen-api", action="store_true", help="检查独立 API Key 路线的 Python 依赖")
    p.add_argument("--with-youtube", action="store_true")
    p.add_argument("--with-packaging", action="store_true")
    p.add_argument("--with-captions", action="store_true", help="检查包内字幕模板及 libass 渲染器")
    p.add_argument("--with-visual-checks", action="store_true", help="检查 Mac Vision 人脸/静音口型工具")
    p.add_argument("--with-corpus-pdf", action="store_true")
    p.add_argument("--with-align", action="store_true")
    args = p.parse_args()
    problems = []
    if sys.version_info < (3, 9): problems.append("Python 3.9+")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name): problems.append(name + " on PATH")
    if shutil.which("ffmpeg"):
        encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
        for name in ("libx264", "aac"):
            if not any(len(line.split()) >= 2 and line.split()[1] == name for line in encoders.splitlines()):
                problems.append("FFmpeg encoder " + name)
    if args.with_heygen or args.with_heygen_cli:
        if os.environ.get("HEYGEN_API_KEY"):
            problems.append("HEYGEN_API_KEY overrides CLI OAuth; unset for web Proofread route")
        local_cli = Path(__file__).resolve().parents[1] / ".tools" / "bin" / "heygen"
        cli = os.environ.get("HEYGEN_CLI") or (str(local_cli) if local_cli.is_file() else shutil.which("heygen"))
        if not cli:
            problems.append("HeyGen CLI (run ./install.sh heygen; on Windows use WSL)")
        else:
            try:
                result = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=15)
                if result.returncode: problems.append("HeyGen CLI --version")
                elif not heygen_cli_contract(cli):
                    problems.append("HeyGen CLI Proofread/SRT/Precision contract (install supported CLI version)")
            except (OSError, subprocess.TimeoutExpired):
                problems.append("HeyGen CLI executable")
    modules = []
    if args.with_heygen_api: modules += ["requests", "requests_toolbelt"]
    if args.with_youtube: modules += ["googleapiclient", "google_auth_oauthlib", "google_auth_httplib2", "httplib2", "google.oauth2", "keyring", "PIL"]
    if args.with_packaging or args.with_captions: modules += ["PIL"]
    if args.with_captions:
        from caption_templates import renderer_ffmpeg, VENDOR
        try:
            print("Caption FFmpeg: " + renderer_ffmpeg())
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            problems.append(str(exc))
        for name in ('SKILL.md', 'scripts/apply_template.py', 'specs/D_contemplative_phrase.json',
                     'fonts/OFL-Montserrat.txt', 'fonts/OFL-Noto.txt'):
            if not (VENDOR / name).is_file(): problems.append('missing bundled caption file: ' + name)
    if args.with_visual_checks:
        if sys.platform != 'darwin' or not shutil.which('swift'):
            problems.append('optional visual checks need macOS Vision and Swift; use visual review on other systems')
    if args.with_corpus_pdf: modules += ["pypdf"]
    for name in modules:
        try: found = importlib.util.find_spec(name)
        except ModuleNotFoundError: found = None
        if found is None: problems.append("Python module " + name)
    if args.with_align:
        root = Path(__file__).resolve().parents[1]
        align_name = ".venv-align-wsl" if sys.platform == "linux" and "microsoft" in os.uname().release.casefold() else ".venv-align"
        align_python = root / align_name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if not align_python.is_file():
            problems.append("alignment environment (run install align)")
        else:
            probe = subprocess.run([str(align_python), "-c", "import stable_whisper, torch, numpy"],
                                   capture_output=True, text=True, timeout=30)
            if probe.returncode: problems.append("alignment modules")
    print("PASS" if not problems else "FAIL: " + ", ".join(problems))
    print("Python " + sys.version.split()[0] + "; platform " + sys.platform)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
