"""Preview a complete spoken sentence before an existing template-rendered film.

Local draft only. Preserves the whole film in order after a brief black bridge.
No new caption renderer, voice generation, upload or inherited final approval.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path
from caption_templates import digest, validate_words
from hook_copy import sentence_ranges
from subtitle_tools import parse_srt


def probe(path):
    return json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_format',
        '-show_streams', '-of', 'json', str(path)], capture_output=True,
        text=True, check=True, timeout=30).stdout)


def verify_finalization(video, words, approved, template, final_receipt, manifest):
    """Read-only compatibility with existing tail-trim receipts, no receipt rewriting."""
    paths = [Path(p).resolve(strict=True) for p in (final_receipt, manifest)]
    final = json.loads(paths[0].read_text());job = json.loads(paths[1].read_text())
    if final.get('manifest_sha256') != digest(paths[1]):
        raise ValueError('finalization manifest hash mismatch')
    if 'audio' in job:
        raise ValueError('replacement audio requires a new alignment binding')
    original = Path(job['video']).resolve(strict=True)
    rendered = Path(template['output']).resolve(strict=True)
    srt = Path(job['srt']).resolve(strict=True)
    if (digest(original) != job['video_sha256'] or job['video_sha256'] != template.get('source_sha256')
            or digest(rendered) != template.get('output_sha256')
            or digest(Path(job['approved_text'])) != digest(approved)):
        raise ValueError('finalization source chain mismatch')
    if (Path(final['output']).resolve() != video or final.get('sha256') != digest(video)
            or final.get('template') != template.get('template')
            or Path(job['out']).resolve() != video.parent):
        raise ValueError('finalization output mismatch')
    aligned = [w for segment in json.loads(words.read_text())['segments'] for w in segment['words']]
    cues = parse_srt(srt)
    if len(aligned) != len(cues) or any(
            ' '.join(c.text.split()) != w['word'] or abs(c.start/1000-float(w['start'])) > .001
            or abs(c.end/1000-float(w['end'])) > .001 for c,w in zip(cues,aligned)):
        raise ValueError('finalization SRT does not match phrase alignment')
    cut = float(job['end_s'])
    if not cues or cues[-1].end/1000+.15 > cut:
        raise ValueError('finalization cuts approved subtitle tail')
    info = probe(video)
    durations = {s['codec_type']: float(s['duration']) for s in info['streams'] if s['codec_type'] in ('audio','video')}
    if set(durations) != {'audio','video'} or any(abs(d-cut) > .05 for d in durations.values()):
        raise ValueError('finalization duration mismatch')
    return {str(p): digest(p) for p in [*paths,original,rendered,srt]}, {
        'kind': 'existing_trim_receipt_and_manifest', 'cut_seconds': cut,
        'manifest_sha256': digest(paths[1]), 'final_receipt_sha256': digest(paths[0]),
        'replacement_audio': False, 'approval_inherited': False}


def plan(video, words, approved, packaging_receipt, sentence_index, *, body_hook_mode,
         finalization_receipt=None, finalization_manifest=None):
    if body_hook_mode != 'none':
        raise ValueError('packaging preview cannot be combined with copy frontloading')
    paths = [Path(p).resolve(strict=True) for p in (video, words, approved, packaging_receipt)]
    video, words, approved, packaging_receipt = paths
    receipt = json.loads(packaging_receipt.read_text())
    hashes = {str(p): digest(p) for p in paths}
    for field, path in [('words_sha256', words), ('approved_text_sha256', approved)]:
        if receipt.get(field) != hashes[str(path)]:
            raise ValueError('template receipt does not match input: ' + field)
    if receipt.get('preserve_text') is not True or receipt.get('decode') != 'PASS':
        raise ValueError('existing verified template render is required')
    finalization = None
    if finalization_receipt is not None or finalization_manifest is not None:
        if not finalization_receipt or not finalization_manifest:
            raise ValueError('finalization requires both receipt and manifest')
        linked, finalization = verify_finalization(video, words, approved, receipt,
                                                  finalization_receipt, finalization_manifest)
        hashes.update(linked)
    elif receipt.get('output_sha256') != hashes[str(video)]:
        raise ValueError('template receipt does not match input: output_sha256')
    info = probe(video)
    picture = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if picture['width'] * 16 != picture['height'] * 9 or not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise ValueError('portrait 9:16 video with audio required')
    duration = float(info['format']['duration'])
    text = approved.read_text(encoding='utf-8-sig')
    aligned = validate_words(json.loads(words.read_text()), text, duration)
    spans = sentence_ranges(text)
    if type(sentence_index) is not int or not 0 <= sentence_index < len(spans):
        raise ValueError('select a complete sentence index')
    compact = lambda s: re.sub(r'\s+', '', s)
    a, b = spans[sentence_index]
    start_offset, end_offset = len(compact(text[:a])), len(compact(text[:b]))
    boundaries = {0: 0}
    offset = 0
    for n, word in enumerate(aligned):
        offset += len(compact(word['word']))
        boundaries[offset] = n + 1
    if start_offset not in boundaries or end_offset not in boundaries:
        raise ValueError('sentence falls inside an alignment unit; align more precisely, never cut the phrase')
    first, stop = boundaries[start_offset], boundaries[end_offset]
    if first == stop:
        raise ValueError('sentence has no aligned speech')
    start, end = aligned[first]['start'], aligned[stop-1]['end']
    # Include at most 80ms of available non-speech margin without taking neighbor speech.
    start = max(float(aligned[first-1]['end']) if first else 0, float(start)-.08)
    end = min(float(aligned[stop]['start']) if stop < len(aligned) else duration, float(end)+.08)
    hook_duration = end-start
    bridge = .2
    total = hook_duration + bridge + duration
    warnings = ['完整句边界不证明语义独立或有吸引力，需听看指代、限定和切点']
    tail = duration - float(aligned[-1]['end'])
    if tail > 1:
        warnings.append('最后字幕后仍有超过1秒画面，可能是未完成尾剪的中间文件；必须核对最终裁切回执')
    if not 2 <= hook_duration <= 4:
        warnings.append('钩子不在约3秒范围；保留完整句，不截断凑时长')
    if not 30 <= total <= 45:
        warnings.append('包含重复句和转场的总时长不在30–45秒；需换候选或另行审核')
    return {'state': 'preview_plan_pending_review', 'hook_mode': 'packaging_preview',
        'body_hook_mode': body_hook_mode, 'sentence_index': sentence_index,
        'hook_text': text[a:b], 'hook_start': start, 'hook_end': end,
        'hook_seconds': hook_duration, 'bridge_seconds': bridge,
        'body_seconds': duration, 'total_seconds_expected': total,
        'tail_after_last_aligned_speech_seconds': tail,
        'body_order_unchanged': True, 'input_hashes': hashes, 'video': str(video),
        'finalization': finalization,
        'width': picture['width'], 'height': picture['height'],
        'source_template': receipt.get('template'), 'warnings': warnings,
        'prior_final_approval_reusable': False, 'external_actions_authorized': False}


def render_preview(proposal, out, ffmpeg='ffmpeg'):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'plan.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2))
    final = out/'preview.mp4'
    try:
        for path, expected in proposal['input_hashes'].items():
            if digest(Path(path)) != expected:
                raise ValueError('input changed since plan')
        a, b = proposal['hook_start'], proposal['hook_end']
        w, h = proposal['width'], proposal['height']
        bridge = proposal['bridge_seconds']
        graph = (f'[0:v]split=2[hv][bv];[0:a]asplit=2[ha][ba];'
            f'[hv]trim=start={a}:end={b},setpts=PTS-STARTPTS,setsar=1,fps=30,format=yuv420p[h];'
            f'[ha]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[ah];'
            f'[bv]setpts=PTS-STARTPTS,setsar=1,fps=30,format=yuv420p[v];'
            f'[ba]asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[ab];'
            f'color=c=black:s={w}x{h}:r=30:d={bridge},format=yuv420p[bridge];'
            f'anullsrc=r=48000:cl=stereo,atrim=duration={bridge}[silence];'
            '[h][ah][bridge][silence][v][ab]concat=n=3:v=1:a=1[outv][outa]')
        cmd = [ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', proposal['video'],
            '-filter_complex', graph, '-map', '[outv]', '-map', '[outa]', '-c:v', 'libx264',
            '-preset', 'fast', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(final)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        (out/'render.log').write_text(result.stderr)
        result.check_returncode()
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(final), '-f', 'null', '-'],
                       capture_output=True, check=True, timeout=600)
        actual = float(probe(final)['format']['duration'])
        if abs(actual-proposal['total_seconds_expected']) > .15:
            raise ValueError('output duration mismatch')
        if any(digest(Path(p)) != sha for p, sha in proposal['input_hashes'].items()):
            raise ValueError('input changed during rendering')
        receipt = {**proposal, 'state': 'technical_pass_T4_review_required', 'output': str(final),
            'output_sha256': digest(final), 'duration_actual': actual, 'decode': 'PASS',
            'input_unchanged': True, 'subtitle_method': 'preserved_existing_template_burn_in',
            'pending': ['listen_complete_sentence', 'natural_transition', 'phone_visual_review', 'T4_new_version_approval']}
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps({'state': 'failed_do_not_deliver', 'error_type': type(exc).__name__}))
        raise
    (out/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('video','words','approved','packaging-receipt','body-hook-mode','out'):
        parser.add_argument('--'+key, required=True)
    parser.add_argument('--sentence-index', type=int, required=True)
    parser.add_argument('--render', action='store_true', help='Render local draft only; no approval or upload')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--finalization-receipt')
    parser.add_argument('--finalization-manifest')
    args = parser.parse_args()
    proposal = plan(args.video, args.words, args.approved, args.packaging_receipt,
                    args.sentence_index, body_hook_mode=args.body_hook_mode,
                    finalization_receipt=args.finalization_receipt,
                    finalization_manifest=args.finalization_manifest)
    if args.render:
        result = render_preview(proposal, args.out, args.ffmpeg)
    else:
        out = Path(args.out);out.mkdir(parents=True, exist_ok=False)
        (out/'plan.json').write_text(json.dumps(proposal, ensure_ascii=False, indent=2));result = proposal
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':main()
