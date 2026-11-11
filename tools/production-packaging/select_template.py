#!/usr/bin/env python3
"""Inspect local source and subtitles, then propose a packaging template."""
import argparse
import json
from math import ceil, floor
from pathlib import Path
import subprocess
import sys
import shutil


ROOT = Path(__file__).resolve().parent

from asset_index import srt


def overlaps(first, second):
    return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]


def frame_geometry(aspect, width, height):
    scaled_height = max(width / aspect, height)
    scaled_width = aspect * scaled_height
    return scaled_width, scaled_height


def assess(samples, frame, reading_area, margin, crop_offset_x=0):
    width, height = frame
    conflicts = {'face_clipped_s': [], 'face_margin_s': [], 'text_intersection_s': []}
    for sample in samples:
        displayed_width, displayed_height = frame_geometry(sample['aspect'], width, height)
        x0 = (width - displayed_width) / 2 - crop_offset_x
        y0 = (height - displayed_height) / 2
        frame_issues = set()
        for face in sample['faces']:
            x1 = x0 + face['x'] * displayed_width
            y1 = y0 + face['y'] * displayed_height
            x2 = x1 + face['width'] * displayed_width
            y2 = y1 + face['height'] * displayed_height
            protected = (x1 - margin, y1 - margin, x2 + margin, y2 + margin)
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
                frame_issues.add('face_clipped_s')
            elif protected[0] < 0 or protected[1] < 0 or protected[2] > width or protected[3] > height:
                frame_issues.add('face_margin_s')
            if overlaps(protected, reading_area):
                frame_issues.add('text_intersection_s')
        for issue in frame_issues:
            conflicts[issue].append(round(sample['time'], 3))
    return conflicts


def fixed_crop_offset(samples, frame, margin):
    width, height = frame
    minimum, maximum = float('-inf'), float('inf')
    for sample in samples:
        displayed_width, _ = frame_geometry(sample['aspect'], width, height)
        extra_width = max(0, (displayed_width - width) / 2)
        minimum = max(minimum, -extra_width)
        maximum = min(maximum, extra_width)
        for face in sample['faces']:
            left = face['x'] * displayed_width - extra_width
            right = left + face['width'] * displayed_width
            minimum = max(minimum, right + margin - width)
            maximum = min(maximum, left - margin)
    # Keep adjustments in two-pixel increments for subsampled video.
    minimum, maximum = ceil(minimum / 2) * 2, floor(maximum / 2) * 2
    return min(max(0, minimum), maximum) if minimum <= maximum else None


def choose(samples, catalog):
    profile = catalog['shorts_preview']
    frame = catalog['frame']
    reading = profile['reading_area_xyxy']
    margin = profile['face_margin_px']
    templates = {template['id']: template for template in catalog['templates']}
    missing = [round(sample['time'], 3) for sample in samples if not sample['faces']]
    multiple = [round(sample['time'], 3) for sample in samples if len(sample['faces']) > 1]
    reasons = {'face_missing_s': missing, 'multiple_faces_s': multiple}
    if not samples or missing:
        return None, reasons
    centered = assess(samples, frame, reading, margin)
    reasons['portrait-caption'] = centered
    if not any(centered.values()):
        return {**templates['portrait-caption'], 'crop_offset_x_px': 0}, reasons
    offset = fixed_crop_offset(samples, frame, margin)
    if offset is not None:
        adjusted = assess(samples, frame, reading, margin, offset)
        reasons['portrait-fixed-offset'] = adjusted
        if not any(adjusted.values()):
            return {**templates['portrait-fixed-offset'], 'crop_offset_x_px': offset}, reasons
    if centered['face_clipped_s']:
        tracking_conflicts = []
        for sample in samples:
            offset = fixed_crop_offset([sample], frame, margin)
            if offset is None or any(assess([sample], frame, reading, margin, offset).values()):
                tracking_conflicts.append(round(sample['time'], 3))
        reasons['portrait-tracking'] = {'no_safe_crop_s': tracking_conflicts}
        if not tracking_conflicts:
            return templates['portrait-tracking'], reasons
    reasons['next_review'] = 'check_portrait_tracking_subtitle_placement_or_source_clip'
    return None, reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('captions', type=Path)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'catalog.json')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    captions, issues = srt(args.captions)
    if not captions or issues:
        parser.error('A nonempty aligned SRT with sequential, nonoverlapping cues is required.')
    if sys.platform != 'darwin' or not shutil.which('swift'):
        parser.error('Automatic face analysis needs macOS Vision and Swift; use visual review on other systems.')
    samples = json.loads(subprocess.check_output(
        ['swift', str(ROOT / 'face-samples.swift'), str(args.video.resolve(strict=True))], timeout=180))
    template, reasons = choose(samples, catalog)
    max_cps = max(len(' '.join(cue['text'].split())) / (cue['end_s'] - cue['start_s']) for cue in captions)
    receipt = {
        'state': 'recommendation' if template else 'needs_visual_review',
        'catalog_version': catalog['version'], 'source': str(args.video.resolve()), 'sample_count': len(samples),
        'output_frame': catalog['frame'], 'caption_cues': len(captions), 'caption_max_cps': round(max_cps, 2),
        'template': template, 'measurements': reasons, 'reading_area_xyxy': catalog['shorts_preview']['reading_area_xyxy'],
        'timing_granularity': 'sentence', 'proposed_text_effect': 'sentence-fade' if template else None,
        'sound': 'original_voice', 'full_frame_qc': 'pending_render',
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
