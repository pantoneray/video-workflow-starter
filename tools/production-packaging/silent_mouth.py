#!/usr/bin/env python3
"""Detect silent mouth movement and trim a safe, verified trailing interval."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parent

from asset_index import srt


def run(args, timeout=180):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)


def sha(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        return digest.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def probe(video):
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)]).stdout)
    picture = next(row for row in data['streams'] if row['codec_type'] == 'video')
    audio = next(row for row in data['streams'] if row['codec_type'] == 'audio')
    return picture, audio


def silence_windows(video, duration, minimum):
    log = run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(video), '-map', '0:a:0',
               '-af', f'silencedetect=n=-35dB:d={minimum}', '-f', 'null', '-']).stderr
    windows = []
    start = None
    for label, value in re.findall(r'silence_(start|end):\s*(-?[\d.]+)', log):
        if label == 'start':
            start = max(0, float(value))
        elif start is not None:
            end = min(duration, float(value))
            if end - start >= 0.35 or (end >= duration - 0.07 and end - start >= minimum):
                windows.append((start, end))
            start = None
    if start is not None and duration - start >= minimum:
        windows.append((start, duration))
    return windows


def find_cut(samples, start, end, caption_end, fps):
    present = [sample for sample in samples if sample.get('aperture') is not None]
    if len(present) < max(3, 0.85 * len(samples)):
        return {'state': 'mouth_unverified'}
    values = sorted(sample['aperture'] for sample in present)
    floor = values[len(values) // 5]
    motion = [sample['time'] for sample in present if sample['aperture'] >= max(0.07, floor + 0.04)]
    result = {'state': 'silent_mouth_motion' if len(motion) >= 2 else 'no_sustained_motion',
              'motion_s': [round(time, 3) for time in motion], 'mouth_aperture_range': [values[0], values[-1]]}
    if result['state'] != 'silent_mouth_motion':
        return result
    earliest = max(start + 0.16, caption_end + 0.12)
    for index in range(1, len(present) - 1):
        sample = present[index]
        cut = round(sample['time'] * fps) / fps
        neighborhood = present[index - 1:index + 2]
        if (earliest <= cut <= min(end - 0.16, motion[0] - 0.07)
                and neighborhood[-1]['time'] - neighborhood[0]['time'] <= 0.18
                and max(row['aperture'] for row in neighborhood) <= floor + 0.025):
            result['cut_s'] = cut
            break
    return result


def inspect(video, captions, minimum_silence=0.35):
    picture, audio = probe(video)
    duration = float(picture['duration'])
    fps = float(Fraction(picture['avg_frame_rate']))
    rows, issues = srt(captions)
    if not rows or issues or rows[-1]['end_s'] > min(duration, float(audio['duration'])):
        raise ValueError('Subtitle timing needs review before trimming.')
    caption_end = rows[-1]['end_s']
    spans = silence_windows(video, duration, minimum_silence)
    landmarks = []
    if spans:
        if sys.platform != 'darwin' or not shutil.which('swift'):
            raise RuntimeError('Automatic mouth analysis needs macOS Vision and Swift; retain pending visual review on other systems.')
        bounds = [str(value) for start, end in spans for value in (start, min(end, duration - 1 / fps))]
        landmarks = json.loads(run(['swift', str(ROOT / 'mouth-samples.swift'), str(video), *bounds]).stdout)
        if len(landmarks) != len(spans):
            raise ValueError('Incomplete mouth samples; visual review is required.')
    events = []
    for (start, end), samples in zip(spans, landmarks):
        event = find_cut(samples, start, end, caption_end, fps)
        event.update(start_s=start, end_s=end, trailing=end >= duration - 2 / fps)
        events.append(event)
    flagged = [event for event in events if event['state'] != 'no_sustained_motion']
    safe_tail = flagged[0] if len(flagged) == 1 and flagged[0]['trailing'] and 'cut_s' in flagged[0] else None
    return {'action': 'trim_tail' if safe_tail else ('review' if flagged else 'pass'),
            'cut_s': safe_tail['cut_s'] if safe_tail else None, 'video_duration_s': duration,
            'subtitle_end_s': caption_end, 'source_sha256': sha(video), 'srt_sha256': sha(captions),
            'silence_threshold_db': -35, 'silent_intervals': events}


def trim(video, captions, decision, output):
    if output.resolve() == video.resolve() or output.exists():
        raise ValueError('Choose a new output file; never overwrite a source or earlier result.')
    if decision['source_sha256'] != sha(video) or decision['srt_sha256'] != sha(captions):
        raise ValueError('The source changed since inspection.')
    if decision['action'] == 'pass':
        return video
    if decision['action'] != 'trim_tail':
        raise ValueError('The recorded silent interval needs visual review before editing.')
    if not (decision['subtitle_end_s'] < decision['cut_s'] < decision['video_duration_s']):
        raise ValueError('The proposed cut must retain every caption and spoken word.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp.mp4')
    run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(video), '-t', f"{decision['cut_s']:.9f}",
         '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16',
         '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', str(temporary)], timeout=420)
    temporary.replace(output)
    return output


def verify(source, captions, decision, output):
    if decision['action'] == 'pass':
        output = source
    current = inspect(output, captions, minimum_silence=0.16)
    picture, _ = probe(output)
    original, _ = probe(source)
    checks = {'silent_mouth_check': current['action'] == 'pass',
              'same_vertical_format': picture['width'] * 16 == picture['height'] * 9 and all(
                  picture[key] == original[key] for key in ('width', 'height', 'avg_frame_rate')),
              'cut_matches': abs(current['video_duration_s'] - (decision['cut_s'] or decision['video_duration_s'])) < 0.04,
              'caption_hash_matches': current['srt_sha256'] == decision['srt_sha256']}
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'])
    checks['decode'] = True

    def audio_prefix(path):
        return run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                    '-t', str(decision['subtitle_end_s']), '-c:a', 'pcm_s16le', '-f', 'hash', '-']).stdout

    checks['audio_identical_through_last_subtitle'] = audio_prefix(source) == audio_prefix(output)
    return {'state': 'awaiting_owner_review' if all(checks.values()) else 'failed_qc', 'checks': checks,
            'media': str(output), 'media_sha256': current['source_sha256'], 'inspection': current}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'trim', 'verify'))
    parser.add_argument('video', type=Path)
    parser.add_argument('captions', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    decision_path = args.run / 'evidence/silent-mouth-before.json'
    output = args.output or args.run / 'output' / f'{args.video.stem}-tail-trimmed.mp4'
    if output.resolve() == args.video.resolve():
        parser.error('The output needs a separate path.')
    if args.action == 'inspect':
        result = inspect(args.video, args.captions)
        save(decision_path, result)
    elif args.action == 'trim':
        media = trim(args.video, args.captions, json.loads(decision_path.read_text()), output)
        result = {'media': str(media)}
    else:
        result = verify(args.video, args.captions, json.loads(decision_path.read_text()), output)
        save(args.run / 'evidence/silent-mouth-after.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('state') == 'failed_qc':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
