#!/usr/bin/env python3
"""Local forced alignment. Source text is authoritative; no ASR rewriting."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

VERSION = '1.0.0'


def compact(text):
    return re.sub(r'\s+', '', text)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def split_clauses(text):
    """Punctuation stays attached; decimals/thousands separators stay intact."""
    pieces, start = [], 0
    for i, char in enumerate(text):
        boundary = char in '，。！？；!?;،؟\n'
        if char in ',.':
            decimal = (i > 0 and i + 1 < len(text)
                       and text[i - 1].isdigit() and text[i + 1].isdigit())
            boundary = not decimal
        if boundary:
            value = text[start:i + 1].strip()
            if value:
                pieces.append(value)
            start = i + 1
    if text[start:].strip():
        pieces.append(text[start:].strip())
    if compact(''.join(pieces)) != compact(text):
        raise ValueError('分句未能完整回拼原文，停止输出。')
    return pieces


def map_chars(raw, expected, offset=0.0):
    chars = []
    for segment in raw['segments']:
        for word in segment.get('words') or []:
            st, en = float(word['start']) + offset, float(word['end']) + offset
            if not math.isfinite(st) or not math.isfinite(en):
                raise ValueError('模型返回非有限时间戳。')
            for char in compact(word['word']):
                chars.append(dict(char=char, start=st, end=en,
                                  probability=word.get('probability')))
    if ''.join(x['char'] for x in chars) != compact(expected):
        raise ValueError('对齐输出与输入文字不完全一致；禁止补字、删字或模糊匹配。')
    return chars


def build_cues(source, chars, duration):
    cues, cursor = [], 0
    for text in split_clauses(source):
        n = len(compact(text))
        span = chars[cursor:cursor + n]
        if ''.join(x['char'] for x in span) != compact(text):
            raise ValueError('字幕字符映射不一致。')
        cues.append(dict(index=len(cues) + 1, text=text,
                         start=min(x['start'] for x in span),
                         end=max(x['end'] for x in span), chars=span))
        cursor += n
    if cursor != len(chars) or compact(''.join(c['text'] for c in cues)) != compact(source):
        raise ValueError('存在遗漏或重复，停止输出。')
    issues = []
    for i, cue in enumerate(cues):
        st, en = cue['start'], cue['end']
        reasons, fatal = [], False
        if not (0 <= st < en <= duration + 0.001) or round(st * 1000) >= round(en * 1000):
            reasons.append('非正时长、负数或越界'); fatal = True
        if i and round(st * 1000) < round(cues[i - 1]['end'] * 1000):
            reasons.append('与前条重叠或倒序'); fatal = True
        spans = cue['chars']
        if any(x['start'] < 0 or x['end'] < x['start'] or x['end'] > duration + 0.001 for x in spans):
            reasons.append('内部字符时间无效'); fatal = True
        if any(b['start'] < a['start'] - 0.001 for a, b in zip(spans, spans[1:])):
            reasons.append('句内字符时间倒序'); fatal = True
        if en - st > 18:
            reasons.append('整句超过18秒，请确认拖腔或模型漂移')
        if any(b['start'] - a['end'] > 3 for a, b in zip(spans, spans[1:])):
            reasons.append('句内字间跳跃超过3秒')
        if sum(x['end'] <= x['start'] for x in spans) / len(spans) > 0.4:
            reasons.append('超过40%的字符为零时长')
        probs = [x['probability'] for x in spans if x['probability'] is not None]
        if probs and sum(probs) / len(probs) < 0.08:
            reasons.append('平均模型置信度低于0.08')
        if reasons:
            issues.append(dict(index=cue['index'], text=cue['text'], start=st, end=en,
                               fatal=fatal, reasons=reasons))
    return cues, issues


def timecode(seconds):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def render_srt(cues):
    return '\n\n'.join(f"{c['index']}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}"
                       for c in cues) + '\n'


def find_ffmpeg(cache_root):
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError as exc:
        raise RuntimeError('缺少 FFmpeg，请先运行安装启动脚本。') from exc
    folder = cache_root / 'bin'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if not target.exists():
        shutil.copy2(bundled, target)
        target.chmod(0o755)
    os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
    return str(target)


def validate_anchors(path, source, duration):
    anchors = json.loads(Path(path).read_text(encoding='utf-8-sig')) if path else []
    if not isinstance(anchors, list):
        raise ValueError('anchors 必须是 JSON 数组。')
    text = compact(source)
    occupied = set()
    result = []
    for item in anchors:
        phrase = compact(item['text'])
        if not phrase:
            raise ValueError('锚点文字不能为空。')
        if 'offset' in item:
            offset = int(item['offset'])
        else:
            matches = [m.start() for m in re.finditer('(?=' + re.escape(phrase) + ')', text)]
            if len(matches) != 1:
                raise ValueError('锚点文字必须唯一匹配；重复原文请指定非空白字符 offset。')
            offset = matches[0]
        if offset < 0 or text[offset:offset + len(phrase)] != phrase:
            raise ValueError('锚点不是原文的完整连续片段。')
        positions = set(range(offset, offset + len(phrase)))
        if occupied & positions:
            raise ValueError('锚点文字区间不能重叠。')
        occupied |= positions
        st, en = float(item['start']), float(item['end'])
        if not (0 <= st < en <= duration):
            raise ValueError('锚点音频范围必须位于完整音频内。')
        result.append(dict(text=item['text'], offset=offset, start=st, end=en))
    return result


def run(args, log=print):
    import importlib.metadata
    audio, txt = Path(args.audio).expanduser().resolve(), Path(args.text).expanduser().resolve()
    if not audio.is_file() or not txt.is_file():
        raise ValueError('音频或 TXT 文件不存在。')
    source = txt.read_text(encoding='utf-8-sig')
    if not compact(source):
        raise ValueError('TXT 为空。')
    output = Path(args.output).expanduser().resolve() if args.output else audio.with_suffix('.srt')
    if output in (audio, txt) or output.suffix.lower() != '.srt':
        raise ValueError('输出必须是独立的 .srt 文件。')
    if output.exists() and not args.overwrite:
        raise ValueError(f'输出已存在：{output}；更换路径或使用 --overwrite。')
    root = Path(args.cache_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(root)
    import numpy as np
    import torch
    import stable_whisper
    torch.set_num_threads(args.threads)
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('当前 PyTorch 环境没有可用 CUDA，请使用 cpu。')
    audio_hash = digest(audio)
    config = dict(audio_sha256=audio_hash, text_sha256=digest(txt), language=args.language,
                  model=args.model, device=args.device, tool_version=VERSION,
                  stable_ts=importlib.metadata.version('stable-ts'),
                  whisper=importlib.metadata.version('openai-whisper'), torch=torch.__version__)
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:24]
    cache = root / key
    cache.mkdir(exist_ok=True)
    log(f'缓存：{cache}')
    wav = cache / 'audio.wav'
    if not wav.exists():
        log('转换为 16 kHz 单声道音频……')
        temp = cache / 'audio.partial.wav'
        proc = subprocess.run([ffmpeg, '-nostdin', '-y', '-v', 'error', '-i', str(audio),
                               '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le',
                               str(temp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode:
            raise RuntimeError(proc.stderr.decode('utf-8', errors='replace'))
        os.replace(temp, wav)
    with wave.open(str(wav), 'rb') as f:
        if f.getnchannels() != 1 or f.getframerate() != 16000 or f.getsampwidth() != 2:
            raise ValueError('缓存 WAV 格式异常，请删除该缓存目录重试。')
        samples = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').astype(np.float32) / 32768
    duration = len(samples) / 16000
    anchors = validate_anchors(args.anchors, source, duration)
    model = None

    def align_cached(data, text, target):
        nonlocal model
        if target.exists():
            log(f'复用对齐缓存：{target.name}')
            return json.loads(target.read_text(encoding='utf-8'))
        if model is None:
            log(f'载入 {args.model} 模型（首次使用会下载模型文件）……')
            model = stable_whisper.load_model(args.model, device=args.device, dq=args.device == 'cpu')
        result = model.align(data, re.sub(r'\s+', ' ', text).strip(), language=args.language,
                             verbose=False, remove_instant_words=False)
        if result is None:
            raise RuntimeError('模型未返回对齐结果。')
        raw = result.to_dict()
        map_chars(raw, text)  # Never cache an altered/missing text sequence.
        save_json(target, raw)
        return raw

    raw = align_cached(samples, source, cache / 'full.json')
    chars = map_chars(raw, source)
    for anchor in anchors:
        log(f"局部重新对齐 {anchor['start']:.2f}–{anchor['end']:.2f} 秒……")
        token = hashlib.sha256(json.dumps(anchor, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
        first, last = round(anchor['start'] * 16000), round(anchor['end'] * 16000)
        local = align_cached(samples[first:last], anchor['text'], cache / f'anchor-{token}.json')
        fixed = map_chars(local, anchor['text'], first / 16000)
        offset = anchor['offset']
        chars[offset:offset + len(fixed)] = fixed
    cues, issues = build_cues(source, chars, duration)
    report = dict(config=config, duration_seconds=duration, cue_count=len(cues),
                  nonwhitespace_characters=len(compact(source)), text_exact=True,
                  anchors=anchors, issues=issues, cues=cues)
    review = cache / 'review.json'
    save_json(review, report)
    for issue in issues:
        log(f"第{issue['index']}条 {issue['start']:.2f}–{issue['end']:.2f}秒："
            + '；'.join(issue['reasons']) + ' | ' + issue['text'])
    if any(i['fatal'] for i in issues):
        raise ValueError(f'时间戳不合法，未写入 SRT。请用局部锚点重新对齐。检查数据：{review}')
    if issues and not args.allow_review:
        raise ValueError(f'存在待复核片段，未写入 SRT。用 --anchors 局部重对齐，或明确使用 '
                         f'--allow-review 导出待复核版本。检查数据：{review}')
    rendered = render_srt(cues)
    # Check rendered output rather than just in-memory word objects.
    recovered = ''.join('\n'.join(block.splitlines()[2:]) for block in rendered.strip().split('\n\n'))
    if compact(recovered) != compact(source):
        raise ValueError('导出回读检查发现文字不一致。')
    atomic_text(output, rendered)
    log(f'已生成：{output}\n{len(cues)} 条；文字及标点完整（忽略排版空白）。'
        + ('存在待复核片段。' if issues else '时间结构检查通过；不等同人工听审。'))
    return dict(output=str(output), cues=len(cues), issues=issues, review=str(review))


def parser():
    p = argparse.ArgumentParser(description='本地音频 + 原文 TXT 强制对齐，保留全部文字和标点。')
    p.add_argument('audio', help='MP3 / M4A / WAV / MP4 等音视频文件')
    p.add_argument('text', help='UTF-8 TXT 原文')
    p.add_argument('--language', default='zh', help='Whisper 语言代码，如 zh / ar / mn / en')
    p.add_argument('--model', default='small', choices=['tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'])
    p.add_argument('--device', default='cpu', choices=['cpu', 'cuda'])
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--output', help='默认在音频旁生成同名 .srt')
    p.add_argument('--cache-dir', default=str(Path.home() / '.cache' / 'faithful-audio-align'))
    p.add_argument('--anchors', help='局部重对齐 JSON；时间是完整音频的绝对秒数')
    p.add_argument('--allow-review', action='store_true', help='允许导出结构合法但有质量疑点的 SRT')
    p.add_argument('--overwrite', action='store_true', help='明确允许覆盖已有目标 SRT')
    return p


if __name__ == '__main__':
    try:
        opts = parser().parse_args()
        if opts.threads < 1:
            raise ValueError('threads 必须大于零。')
        run(opts)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        sys.exit(2)
