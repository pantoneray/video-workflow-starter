#!/usr/bin/env python3
"""Create a bounded H.264/AAC upload copy without changing the source clip."""
import argparse
import json
import math
import subprocess
from pathlib import Path

from check_output import inspect, sha256

DEFAULT_MAX_BYTES = 48_000_000


def prepare(source, output, max_bytes=DEFAULT_MAX_BYTES, max_height=None):
    source, output = Path(source), Path(output)
    if not source.is_file() or output.suffix.lower() != ".mp4":
        raise ValueError("须提供已有视频和新的 MP4 输出路径")
    if source.resolve() == output.resolve() or output.exists() or Path(str(output) + ".receipt.json").exists():
        raise FileExistsError("输出或回执已存在，或输出等于源片；请使用新路径")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 100_000 <= max_bytes <= 50_000_000:
        raise ValueError("文件预算须为 100000–50000000 字节；默认保守预算 48000000 字节")
    if max_height is not None and (not isinstance(max_height, int) or max_height < 160 or max_height % 2):
        raise ValueError("最大高度须为不小于 160 的偶数")
    source_qc = inspect(source)
    if source_qc["decode"] != "PASS" or not source_qc["video"] or not source_qc["audio"]:
        raise ValueError("上传副本的源片须完整解码且有画面、原声")
    duration = source_qc["duration_s"]
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("源片时长无效")
    # Reserve container overhead and audio; retry with less video bitrate if needed.
    audio_kbps = 192
    video_kbps = int(max_bytes * 8 * .88 / duration / 1000 - audio_kbps)
    if video_kbps < 150:
        raise ValueError("预算过小，无法保留可用的视频与原声；请增大预算")
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_video = f"scale=-2:min(ih\\,{max_height})" if max_height else None
    last_size = None
    for attempt in range(3):
        trial = output.with_name(output.stem + f".attempt-{attempt+1}.mp4")
        if trial.exists():
            raise FileExistsError("已有未完成的转码副本；请核查后使用新输出名")
        bitrate = max(150, int(video_kbps * (.72 ** attempt)))
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(source),
                   "-map", "0:v:0", "-map", "0:a:0"]
        if filter_video:
            command += ["-vf", filter_video]
        command += ["-c:v", "libx264", "-preset", "medium", "-b:v", f"{bitrate}k",
                    "-maxrate", f"{bitrate}k", "-bufsize", f"{bitrate*2}k", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-movflags", "+faststart",
                    "-sn", "-dn", "-n", str(trial)]
        try:
            run = subprocess.run(command, capture_output=True, text=True,
                                 timeout=max(180, int(duration * 20)))
            if run.returncode or not trial.is_file():
                raise RuntimeError("FFmpeg 制作上传副本失败；请核对源片编码和磁盘空间")
            last_size = trial.stat().st_size
            if last_size > max_bytes:
                trial.unlink()
                continue
            qc = inspect(trial)
            if (qc["decode"] != "PASS" or not qc["audio"] or not qc["video"]
                    or qc["video"].get("codec_name") != "h264"
                    or qc["audio"].get("codec_name") != "aac"
                    or abs(qc["duration_s"] - duration) > .5):
                raise RuntimeError("上传副本解码、音轨、编码或时长检查失败")
            if sha256(source) != source_qc["sha256"]:
                raise RuntimeError("源片在转码期间发生变化，已停止")
            trial.replace(output)
            result = {"status": "local_upload_copy_ready_not_remote_accepted",
                      "source_file": str(source.resolve()), "source_sha256": source_qc["sha256"],
                      "output_file": str(output.resolve()), "output_sha256": sha256(output),
                      "output_bytes": output.stat().st_size, "max_bytes": max_bytes,
                      "duration_s": qc["duration_s"], "video_codec": "h264", "audio_codec": "aac",
                      "max_height": max_height, "source_preserved": True,
                      "next": "以此副本重新运行 speech prepare；预检、HeyGen 上传及费用授权都绑定此文件哈希"}
            with Path(str(output) + ".receipt.json").open("x", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.write("\n")
            return result
        finally:
            trial.unlink(missing_ok=True)
    raise ValueError(f"三次压制后仍超出文件预算；最后一次 {last_size} 字节。可显式缩小画面高度或调整素材")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-height", type=int, help="可选，显式缩小高度；默认保留源片尺寸")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.out, args.max_bytes, args.max_height), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
