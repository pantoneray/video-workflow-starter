#!/usr/bin/env python3
"""Find continuous 30–45 s visual candidates; leave visual judgement to the agent."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from slice import probe_video, sha256

SCENE = re.compile(r'pts_time:([0-9.]+)')
FREEZE_START = re.compile(r'freeze_start: ([0-9.]+)')
FREEZE_END = re.compile(r'freeze_end: ([0-9.]+)')
BLACK = re.compile(r'black_start:([0-9.]+) black_end:([0-9.]+)')


def ffmpeg_scan(source, start, length, filter_string):
    result = subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-ss', str(start), '-i', str(source),
                             '-t', str(length), '-an', '-vf', 'setpts=PTS-STARTPTS,' + filter_string,
                             '-f', 'null', '-'], capture_output=True, text=True,
                            timeout=max(120, int(length * 8)))
    if result.returncode:
        raise RuntimeError('FFmpeg 分析失败：' + result.stderr[-300:])
    return result.stderr


def merge(intervals):
    result = []
    for a, b in sorted(intervals):
        if result and a <= result[-1][1]: result[-1][1] = max(result[-1][1], b)
        else: result.append([a, b])
    return result


def clean_windows(length, blocked, minimum, maximum, limit=0):
    intervals = merge([(max(0, a), min(length, b)) for a, b in blocked if b > 0 and a < length])
    gaps = []
    cursor = 0.0
    for a, b in intervals:
        if a - cursor >= minimum: gaps.append((cursor, a))
        cursor = max(cursor, b)
    if length - cursor >= minimum: gaps.append((cursor, length))
    windows = []
    for a, b in gaps:
        cursor = a
        while b - cursor >= minimum:
            end = min(cursor + maximum, b)
            windows.append((cursor, end))
            cursor = end
        # Keep a tail candidate when a short remainder would otherwise be lost.
        if cursor < b and b - a >= minimum:
            tail = (max(a, b - maximum), b)
            if tail not in windows:
                windows.append(tail)
    return windows[:limit] if limit else windows


def scan(args):
    source = Path(args.input).expanduser().resolve()
    if not source.is_file(): raise ValueError('源视频不存在')
    duration, width, height = probe_video(source)
    rules = json.loads(Path(args.rules).read_text(encoding='utf-8'))
    minimum, maximum = float(rules['min_seconds']), float(rules['max_seconds'])
    if not 30 <= minimum <= maximum <= 45: raise ValueError('此入口只接受 30–45 秒范围')
    if int(rules['preview_frames']) < 2 or args.max_candidates < 0: raise ValueError('预览帧数至少为 2，候选上限须非负，0 表示不限')
    if min(width, height) < int(rules['min_short_side']): raise ValueError('源视频分辨率低于规则下限')
    start = float(args.scan_start)
    length = min(float(args.scan_seconds), duration-start) if args.scan_seconds is not None else duration-start
    if not all(math.isfinite(x) for x in (start, length)) or start < 0 or length < minimum: raise ValueError('扫描范围不足 30 秒')
    margin = float(rules['boundary_margin_seconds'])
    scene_log = ffmpeg_scan(source, start, length, "select='gt(scene,{})',showinfo".format(rules['scene_threshold']))
    defect_log = ffmpeg_scan(source, start, length, 'freezedetect=n={}dB:d={},blackdetect=d={}:pix_th=0.10'.format(
        rules['freeze_noise_db'], rules['freeze_min_seconds'], rules['black_min_seconds']))
    cuts = [float(x) for x in SCENE.findall('\n'.join(line for line in scene_log.splitlines() if 'showinfo' in line and 'pts_time:' in line))]
    blocked = [(t-margin, t+margin) for t in cuts]
    starts = [float(x) for x in FREEZE_START.findall(defect_log)]
    ends = [float(x) for x in FREEZE_END.findall(defect_log)]
    blocked += [(a-margin, b+margin) for a, b in zip(starts, ends)]
    if len(starts) > len(ends):
        blocked.append((starts[-1]-margin, length))
    blocked += [(float(a)-margin, float(b)+margin) for a, b in BLACK.findall(defect_log)]
    windows = clean_windows(length, blocked, minimum, maximum, int(args.max_candidates))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    previews = out / 'previews'; previews.mkdir()
    candidates = []
    for index, (a, b) in enumerate(windows, 1):
        s, e = start+a, start+b
        frames = []
        for j in range(int(rules['preview_frames'])):
            position = s + 1.0 + (e-s-2.0) * j / (int(rules['preview_frames'])-1)
            path = previews / f'candidate-{index:02d}-frame-{j+1:02d}.jpg'
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-ss', str(position),
                                     '-i', str(source), '-frames:v', '1', '-vf', 'scale=480:-2', '-q:v', '4', '-n', str(path)],
                                    capture_output=True, text=True, timeout=90)
            if result.returncode or not path.is_file(): raise RuntimeError('抽帧失败（秒 %s）：' % position + result.stderr[-800:])
            frames.append(str(path.resolve()))
        candidates.append({'id': index, 'start': round(s, 3), 'end': round(e, 3),
                           'duration': round(e-s, 3), 'preview_frames': frames,
                           'visual_review': 'required_before_choose'})
    report = {'source': str(source), 'rules': str(Path(args.rules).resolve()), 'scan_start': start,
              'scan_seconds': length, 'source_duration': duration,
              'full_source_covered': start == 0 and abs(length-duration) < 0.01,
              'covered_intervals': [[start, start+length]],
              'source_size': source.stat().st_size, 'source_mtime_ns': source.stat().st_mtime_ns,
              'candidate_limit': args.max_candidates, 'action_review_required': True,
              'detected_scene_cuts': len(cuts), 'detected_freezes': len(starts),
              'detected_black_intervals': len(BLACK.findall(defect_log)), 'candidates': candidates,
              'note': '机械检测不能证明构图、动作、起止自然；Agent 须查看候选帧，成片仍需检查'}
    (out / 'candidates.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


ACTION_CHECKS = ("scratch_neck", "scratch_head", "drinking", "raised_hand",
                 "palms_together", "face_obstruction", "head_down")


def selection(report, ids):
    if len(set(ids)) != len(ids):
        raise ValueError('候选 ID 重复')
    selected = []
    for cid in ids:
        candidate = next((c for c in report['candidates'] if c['id'] == cid), None)
        if candidate is None:
            raise ValueError('候选 ID 不存在')
        selected.append(candidate)
    return sorted(selected, key=lambda c: c['start'])


def review(args):
    report_path = Path(args.candidates)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    selected = selection(report, args.candidate_id)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    entries = []
    for c in selected:
        preview = out / ('candidate-%04d.mp4' % c['id'])
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                        '-ss', str(c['start']), '-i', report['source'], '-t', str(c['end']-c['start']),
                        '-an', '-vf', 'scale=480:-2', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-crf', '26', str(preview)], check=True, timeout=300)
        entries.append({'candidate_id': c['id'], 'start': c['start'], 'end': c['end'],
                        'preview_video': str(preview.resolve()), 'watched_full_candidate': False,
                        'existing_visual_rules_pass': False,
                        'actions': {name: 'unreviewed' for name in ACTION_CHECKS},
                        'decision': 'pending', 'reviewer': '', 'notes': ''})
    template = {'candidates_sha256': sha256(report_path), 'reviews': entries,
                'instructions': '连续查看整段；逐项标记 acceptable/excessive/frequent/uncertain，'
                                '只有 acceptable 可选。头部动作不能仅凭五张预览判断；不确定则拒绝。'
                                'notes 记录动作时段及判断依据；不伪造已经观看。'}
    (out / 'review.json').write_text(json.dumps(template, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return template


def choose(args):
    report_path = Path(args.candidates)
    report = json.loads(report_path.read_text(encoding='utf-8'))
    ids = args.candidate_id if isinstance(args.candidate_id, list) else [args.candidate_id]
    selected = selection(report, ids)
    if not args.visual_reviewed or not getattr(args, 'review_file', None):
        raise ValueError('先连续查看候选并记录动作审核，再传 --visual-reviewed --review-file')
    reviewed = json.loads(Path(args.review_file).read_text(encoding='utf-8'))
    if reviewed.get('candidates_sha256') != sha256(report_path):
        raise ValueError('动作审核与本次候选报告不匹配')
    cuts = []
    for candidate in selected:
        entries = [x for x in reviewed.get('reviews', []) if x.get('candidate_id') == candidate['id']]
        if len(entries) != 1:
            raise ValueError('每个候选须有且只有一条动作审核')
        item = entries[0]
        if (item.get('start') != candidate['start'] or item.get('end') != candidate['end']
                or item.get('watched_full_candidate') is not True
                or item.get('existing_visual_rules_pass') is not True
                or item.get('decision') != 'approve' or not str(item.get('reviewer') or '').strip()
                or not str(item.get('notes') or '').strip()
                or any(item.get('actions', {}).get(k) != 'acceptable' for k in ACTION_CHECKS)):
            raise ValueError('候选 %s 未通过完整画面及动作审核（特殊手势/频繁低头）' % candidate['id'])
        if cuts and candidate['start'] < cuts[-1]['end'] - 0.001:
            raise ValueError('选择的候选重叠；请选取不重复的片段')
        cuts.append({'start': candidate['start'], 'end': candidate['end'], 'label': 'selected',
                     'candidate_id': candidate['id'], 'note': item['notes'],
                     'review_file_sha256': sha256(args.review_file)})
    with Path(args.out).open('x', encoding='utf-8') as f:
        json.dump(cuts, f, ensure_ascii=False, indent=2)
        f.write('\n')
    return {'cuts': str(Path(args.out).resolve()), 'source': report['source'], 'candidate_ids': ids}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('scan')
    a.add_argument('--input', required=True); a.add_argument('--rules', required=True); a.add_argument('--out', required=True)
    a.add_argument('--scan-start', type=float, default=0); a.add_argument('--scan-seconds', type=float, default=None)
    a.add_argument('--max-candidates', type=int, default=0)
    a = sub.add_parser('review')
    a.add_argument('--candidates', required=True); a.add_argument('--candidate-id', type=int, nargs='+', required=True)
    a.add_argument('--out', required=True)
    a = sub.add_parser('choose')
    a.add_argument('--candidates', required=True); a.add_argument('--candidate-id', type=int, nargs='+', required=True)
    a.add_argument('--review-file', required=True)
    a.add_argument('--visual-reviewed', action='store_true'); a.add_argument('--out', required=True)
    args = p.parse_args()
    try: result = {'scan': scan, 'review': review, 'choose': choose}[args.action](args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError) as exc: p.exit(2, str(exc)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
