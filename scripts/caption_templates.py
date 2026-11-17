#!/usr/bin/env python3
"""Validate a task and invoke the bundled caption renderer; never fetch a repository."""
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
from caption_selection import plan as caption_plan

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'tools' / 'shorts-caption-templates'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def filters_available(executable):
    result = subprocess.run([str(executable), '-hide_banner', '-filters'],
                            capture_output=True, text=True, timeout=30, check=True)
    names = {row.split()[1] for row in result.stdout.splitlines() if len(row.split()) >= 2}
    return {'ass', 'zoompan', 'loudnorm', 'sidechaincompress'} <= names


def renderer_ffmpeg(explicit=None):
    selected = explicit or os.environ.get('VIDEO_WORKFLOW_FFMPEG')
    if selected:
        found = shutil.which(selected)
        if not found or not filters_available(found):
            raise ValueError('Configured FFmpeg lacks caption/audio filters')
        return str(Path(found).resolve())
    system = shutil.which('ffmpeg')
    if system and filters_available(system):
        return str(Path(system).resolve())
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if filters_available(bundled):
            return str(Path(bundled).resolve())
    except ImportError:
        pass
    raise ValueError('Caption rendering needs FFmpeg with libass; run install packaging')


def validate_words(data, approved, duration):
    words = [w for segment in data['segments'] for w in segment.get('words', [])]
    if not words:
        raise ValueError('Actual aligned word timestamps are required')
    compact = lambda s: re.sub(r'\s+', '', s)
    if compact(''.join(w['word'] for w in words)) != compact(approved):
        raise ValueError('Aligned words differ from approved text, including case or punctuation')
    last_end = 0.0
    for word in words:
        start, end = float(word['start']), float(word['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration + .001):
            raise ValueError('Invalid or out-of-range word timestamp')
        if start < last_end - .001:
            raise ValueError('Overlapping word timestamps need review')
        # These sequences have special meaning in ASS and would not display literally.
        if any(c in word['word'] for c in '{}\\'):
            raise ValueError('ASS control characters require a literal-text renderer')
        last_end = end
    return words


def render(video, words, approved_text, out, template='auto', language='en', ffmpeg=None, spec=None,
           shift_up=80, highlight=None, course=None, contrast=None, phrase_alignment=False):
    paths = [Path(p).expanduser().resolve(strict=True) for p in (video, words, approved_text)]
    video, words, approved_text = paths
    before = {str(p): digest(p) for p in paths}
    info = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                     '-of', 'json', str(video)], capture_output=True, text=True,
                                    check=True, timeout=30).stdout)
    duration = float(info['format']['duration'])
    if not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise ValueError('An audio track is required for this spoken-caption workflow')
    data = json.loads(words.read_text(encoding='utf-8-sig'))
    validate_words(data, approved_text.read_text(encoding='utf-8-sig'), duration)
    if template == 'A':
        raise ValueError('Template A uses a landscape window; this workflow requires full-bleed portrait')
    executable = renderer_ffmpeg(ffmpeg)
    out = Path(out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)  # exclusive per-run output, also prevents duplicate runs
    try:
        settings, background = caption_plan(video, VENDOR, template=template, spec=spec,
                                            shift_up=shift_up, highlight=highlight, course=course,
                                            contrast=contrast, ffmpeg=executable)
    except Exception as exc:
        (out / 'background-check.json').write_text(json.dumps({
            'state': 'failed_render_not_started', 'error_type': type(exc).__name__,
            'source_sha256': before[str(video)]}, indent=2), encoding='utf-8')
        raise
    background['source_sha256'] = before[str(video)]
    (out / 'background-check.json').write_text(json.dumps(background, ensure_ascii=False, indent=2), encoding='utf-8')
    if phrase_alignment:
        settings['captions'].update(animation='phrase', max_words=1, max_chars_latin=64)
    local_spec = out / 'template.json'
    local_spec.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    cmd = [sys.executable, str(VENDOR / 'scripts' / 'apply_template.py'),
           '--template', str(local_spec), '--video', str(video), '--words', str(words),
           '--lang', language.split('-')[0].lower(), '--out', 'final.mp4', '--preserve-text',
           '--static-camera', '--ffmpeg', executable, '--preview', str(min(.5, duration / 2))]
    result = subprocess.run(cmd, cwd=out, capture_output=True, text=True, timeout=1900)
    (out / 'render.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Caption renderer failed; inspect render.log in the output folder')
    final = out / 'final.mp4'
    subprocess.run([executable, '-nostdin', '-v', 'error', '-xerror', '-i', str(final), '-f', 'null', '-'],
                   capture_output=True, text=True, check=True, timeout=600)
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                      '-of', 'json', str(final)], capture_output=True, text=True,
                                     check=True, timeout=30).stdout)
    picture = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    if (picture['width'], picture['height']) != (1080, 1920):
        raise ValueError('Rendered frame is not 1080x1920')
    if abs(float(probe['format']['duration']) - duration) > .1:
        raise ValueError('Unexpected duration change')
    if before != {str(p): digest(p) for p in paths}:
        raise ValueError('Input changed during rendering')
    receipt = {'state': 'technical_pass_visual_review_pending', 'template': settings['id'],
               'source_sha256': before[str(video)], 'words_sha256': before[str(words)],
               'approved_text_sha256': before[str(approved_text)], 'output': str(final),
               'output_sha256': digest(final), 'preserve_text': True, 'static_camera': True,
               'ffmpeg': executable, 'decode': 'PASS', 'input_unchanged': True,
               'alignment_provenance': 'caller_supplied_requires_actual_audio_alignment',
               'alignment_unit': 'phrase' if phrase_alignment else 'word',
               'caption_y': settings['captions']['y_center'], 'highlight': settings['captions'].get('highlight'),
               'course_badge': settings.get('course_badge'), 'contrast': background['applied_contrast'],
               'background_check': str(out / 'background-check.json'),
               'template_selection': background['selection'],
               'pending': ['face_and_head_safety', 'phone_readability', 'listen_and_lip_sync',
                           'silent_mouth_check', 'loudness_measurement']}
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'words', 'approved-text', 'out'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--template', choices=['auto'] + list('ABCDEF'), default='auto')
    p.add_argument('--language', required=True)
    p.add_argument('--spec', help='Optional local copy of a full-bleed template specification')
    p.add_argument('--ffmpeg', help='Optional executable with libass; otherwise auto-detect locally')
    p.add_argument('--shift-up', type=float, default=80, help='Pixels upward from chosen spec; use 0 for original position')
    p.add_argument('--highlight', help='yellow, green or #RRGGBB for templates with emphasis color')
    p.add_argument('--contrast', choices=['outline', 'box', 'template'], help='Override contrast; template keeps original styling')
    p.add_argument('--course-name')
    p.add_argument('--course-source')
    p.add_argument('--course-confirmed', action='store_true')
    p.add_argument('--phrase-alignment', action='store_true', help='Input items are aligned phrases, not individual word timestamps')
    args = p.parse_args()
    course = {'text': args.course_name, 'source': args.course_source, 'confirmed': args.course_confirmed} if args.course_name else None
    print(json.dumps(render(args.video, args.words, args.approved_text, args.out, args.template,
                            args.language, args.ffmpeg, args.spec, args.shift_up, args.highlight, course, args.contrast,
                            args.phrase_alignment), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
