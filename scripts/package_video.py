#!/usr/bin/env python3
"""Burn reviewed SRT onto a new video using Pillow overlays and FFmpeg."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from check_output import inspect
from subtitle_tools import parse_srt


def render_caption(text, target, font_path, font_size, safe_bottom, out):
    from PIL import Image, ImageDraw, ImageFont
    width, height = target
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), font_size)
    available = width - max(80, int(width * .12))
    lines, current = [], ""
    for character in text:
        if character == "\n":
            lines.append(current)
            current = ""
            continue
        trial = current + character
        if current and draw.textlength(trial, font=font) > available:
            lines.append(current)
            current = character
        else:
            current = trial
    if current:
        lines.append(current)
    line_height = int(font_size * 1.35)
    block_height = line_height * len(lines)
    y = height - safe_bottom - block_height
    if y < int(height * .55):
        raise ValueError("字幕太长或字体过大，超过下半屏安全区；请重新断句")
    for line in lines:
        x = (width - draw.textlength(line, font=font)) / 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=max(2, font_size // 18), stroke_fill="#1b1d21")
        y += line_height
    image.save(out)


def package(video, srt, config, out):
    video, srt, out = Path(video), Path(srt), Path(out)
    if not video.is_file() or not srt.is_file() or out.exists():
        raise ValueError("视频/字幕不存在，或输出目录已存在")
    if "planned-not-final" in srt.name:
        raise ValueError("预估 SRT 不能当作最终音频对齐字幕")
    cues = parse_srt(srt)
    source_qc = inspect(video)
    if source_qc["decode"] != "PASS" or not source_qc["audio"]:
        raise ValueError("输入成片须可完整解码且有原声")
    if cues[-1].end / 1000 > source_qc["duration_s"] + .1:
        raise ValueError("字幕超出成片时长")
    width = int(config.get("width") or source_qc["video"]["width"])
    height = int(config.get("height") or source_qc["video"]["height"])
    if width < 160 or height < 160 or width % 2 or height % 2:
        raise ValueError("输出宽高须为不小于 160 的偶数")
    font = Path(config["font_path"]).expanduser()
    if not font.is_file():
        raise FileNotFoundError("请在包外配置本机可用、支持目标语言的字体文件")
    font_size = int(config.get("font_size") or max(24, round(width * .045)))
    safe_bottom = int(config.get("safe_bottom") or round(height * .12))
    fps = int(config.get("fps") or 30)
    if not 12 <= fps <= 60 or font_size < 10 or safe_bottom < 0:
        raise ValueError("包装配置参数无效")
    intro = Path(config["intro_path"]).expanduser() if config.get("intro_path") else None
    outro = Path(config["outro_path"]).expanduser() if config.get("outro_path") else None
    music = Path(config["music_path"]).expanduser() if config.get("music_path") else None
    for extra in (intro, outro, music):
        if extra and not extra.is_file():
            raise FileNotFoundError("可选片头/片尾/配乐不存在：" + str(extra))
    music_volume = float(config.get("music_volume", .12))
    if not math.isfinite(music_volume) or not 0 <= music_volume <= .5:
        raise ValueError("配乐音量须在 0 到 0.5 之间")
    if music_volume == 0:
        music = None
    fade = float(config.get("transition_seconds") or 0)
    if not math.isfinite(fade) or fade < 0:
        raise ValueError("转场淡入淡出时长须为非负有限数")
    out.mkdir(parents=True)
    overlays = out / "caption-overlays"
    overlays.mkdir()
    for index, cue in enumerate(cues):
        render_caption(cue.text, (width, height), font, font_size, safe_bottom,
                       overlays / f"cue-{index+1:04d}.png")
    postprocess = any((intro, outro, music))
    output = out / ("body.mp4" if postprocess else "final.mp4")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(video)]
    for index in range(len(cues)):
        command += ["-i", str(overlays / f"cue-{index+1:04d}.png")]
    chain = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[base]"]
    current = "base"
    for index, cue in enumerate(cues, 1):
        label = f"v{index}"
        start, end = cue.start / 1000, cue.end / 1000
        chain.append(f"[{current}][{index}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{label}]")
        current = label
    chain.append(f"[{current}]fps={fps},format=yuv420p[vout]")
    command += ["-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", "-n", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=max(180, int(source_qc["duration_s"] * 20)))
    if result.returncode:
        raise RuntimeError("包装 FFmpeg 失败：" + result.stderr[-500:])
    body_qc = inspect(output)
    if body_qc["decode"] != "PASS" or abs(body_qc["duration_s"] - source_qc["duration_s"]) > .5:
        raise RuntimeError("包装后解码或时长验收失败")
    expected_duration = source_qc["duration_s"]
    if postprocess:
        segments = [item for item in (intro, output, outro) if item]
        segment_qc = [inspect(item) for item in segments]
        if any(item["decode"] != "PASS" or not item["audio"] for item in segment_qc):
            raise ValueError("片头/片尾须可解码且含音轨；无声片请先添加静音轨")
        expected_duration = sum(item["duration_s"] for item in segment_qc)
        if fade < 0 or any(fade * 2 >= item["duration_s"] for item in segment_qc):
            raise ValueError("转场淡入淡出时长须小于每段时长的一半")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
        for item in segments:
            cmd += ["-i", str(item)]
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music)]
        filters = []
        for index, item in enumerate(segment_qc):
            duration = item["duration_s"]
            vf = (f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                  f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p")
            af = f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            if fade:
                vf += f",fade=t=in:st=0:d={fade:.3f},fade=t=out:st={duration-fade:.3f}:d={fade:.3f}"
                af += f",afade=t=in:st=0:d={fade:.3f},afade=t=out:st={duration-fade:.3f}:d={fade:.3f}"
            filters += [vf + f"[v{index}]", af + f"[a{index}]"]
        feeds = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        filters.append(feeds + f"concat=n={len(segments)}:v=1:a=1[vcat][acat]")
        audio_label = "[acat]"
        if music:
            filters.append(f"[{len(segments)}:a:0]volume={music_volume:.3f},atrim=duration={expected_duration:.3f}[music]")
            filters.append("[acat][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[aout]")
            audio_label = "[aout]"
        final = out / "final.mp4"
        cmd += ["-filter_complex", ";".join(filters), "-map", "[vcat]", "-map", audio_label,
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac",
                "-b:a", "192k", "-movflags", "+faststart", "-n", str(final)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(180, int(expected_duration * 20)))
        if result.returncode:
            raise RuntimeError("片头片尾/配乐包装失败：" + result.stderr[-500:])
        output = final
    final_qc = inspect(output)
    if final_qc["decode"] != "PASS" or abs(final_qc["duration_s"] - expected_duration) > .5:
        raise RuntimeError("最终包装解码或时长验收失败")
    receipt = {"source_file": str(video.resolve()), "source_sha256": source_qc["sha256"],
               "subtitle_file": str(srt.resolve()), "subtitle_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
               "font_file": str(font.resolve()), "font_size": font_size, "safe_bottom": safe_bottom,
               "cues": len(cues), "output": str(output.resolve()), "output_qc": final_qc,
               "intro": str(intro.resolve()) if intro else None, "outro": str(outro.resolve()) if outro else None,
               "music": str(music.resolve()) if music else None,
               "audio_alignment": "requires_reviewed_srt_and_listening_evidence_outside_this_script"}
    (out / "package-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video", required=True)
    p.add_argument("--reviewed-srt", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    result = package(args.video, args.reviewed_srt, json.loads(Path(args.config).read_text(encoding="utf-8")), args.out)
    print(json.dumps({"output": result["output"], "cues": result["cues"], "decode": result["output_qc"]["decode"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
