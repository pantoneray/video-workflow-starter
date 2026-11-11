#!/usr/bin/env python3
"""Prepare single-segment generation inputs and validate final bilingual SRT pairs.

Standard library only. Does not transcribe, translate, force-align, or publish.
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


TIMING = re.compile(
    r"^(\d{2,}):([0-5]\d):([0-5]\d),(\d{3}) --> "
    r"(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})$"
)


@dataclass(frozen=True)
class Cue:
    start: int
    end: int
    text: str


def read_text(path):
    return Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def normalized(text):
    # Do not normalize punctuation, case, spelling or direction markers.
    return "".join(unicodedata.normalize("NFC", text).split())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def duration_ms(value):
    try:
        seconds = Decimal(value)
        if not seconds.is_finite() or seconds <= 0:
            raise ValueError("duration must be finite and positive")
        result = int((seconds * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("invalid duration") from exc
    if result <= 0:
        raise ValueError("duration must be at least 1 millisecond")
    return result


def timestamp(milliseconds):
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def time_value(parts):
    hour, minute, second, ms = map(int, parts)
    return ((hour * 60 + minute) * 60 + second) * 1000 + ms


def parse_srt(path):
    text = read_text(path).strip()
    if not text:
        raise ValueError(f"empty SRT: {path}")
    cues = []
    for index, block in enumerate(re.split(r"\n[ \t]*\n", text), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(index):
            raise ValueError(f"{path}: cue {index} must have consecutive numbering and text")
        timing = TIMING.fullmatch(lines[1].strip())
        if timing is None:
            raise ValueError(f"{path}: cue {index} has invalid SRT timecode")
        start, end = time_value(timing.groups()[:4]), time_value(timing.groups()[4:])
        body = "\n".join(lines[2:]).strip()
        if end <= start:
            raise ValueError(f"{path}: cue {index} has zero/negative duration")
        if cues and start < cues[-1].end:
            raise ValueError(f"{path}: cue {index} overlaps the previous cue")
        if not body or not any(char.isalnum() for char in body):
            raise ValueError(f"{path}: cue {index} has empty or punctuation-only text")
        if re.search(r"</?(?:b|i|u|font)\b[^>]*>|\{\\", body, flags=re.IGNORECASE):
            raise ValueError(f"{path}: cue {index} includes subtitle formatting; supply plain text SRT")
        cues.append(Cue(start, end, body))
    return cues


def full_text(cues):
    return " ".join(cue.text.replace("\n", " ") for cue in cues)


def render_single(text, end):
    return f"1\n00:00:00,000 --> {timestamp(end)}\n{text}\n\n"


def prepare(args):
    source = parse_srt(args.source_srt)
    target = parse_srt(args.target_srt)
    end = duration_ms(args.duration_seconds)
    output = Path(args.output_dir)
    source_text, target_text = full_text(source), full_text(target)
    canonical_checks = {}
    for label, content, canonical_path in (
        ("source", source_text, args.source_text),
        ("target", target_text, args.target_text),
    ):
        canonical_checks[label] = False
        if canonical_path:
            canonical = normalized(read_text(canonical_path))
            if not canonical or normalized(content) != canonical:
                raise ValueError(f"{label}: generation SRT does not preserve complete canonical text")
            canonical_checks[label] = True
    files = {
        "source-single.srt": render_single(source_text, end),
        "target-single.srt": render_single(target_text, end),
        "bilingual-single.srt": render_single(target_text + "\n" + source_text, end),
    }
    manifest = {
        "purpose": "generation_input_only_not_final_audio_alignment",
        "segment_count": 1,
        "start_ms": 0,
        "end_ms": end,
        "source_input_sha256": digest(Path(args.source_srt).read_bytes()),
        "target_input_sha256": digest(Path(args.target_srt).read_bytes()),
        "source_text_sha256": digest(normalized(source_text).encode("utf-8")),
        "target_text_sha256": digest(normalized(target_text).encode("utf-8")),
        "source_input_cues": len(source),
        "target_input_cues": len(target),
        "canonical_text_checked": canonical_checks,
        "outputs_sha256": {name: digest(content.encode("utf-8")) for name, content in files.items()},
    }
    files["generation-input-check.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if output.exists() and not output.is_dir():
        raise ValueError("output path is not a directory")
    conflicts = [name for name in files if (output / name).exists()]
    if conflicts:
        raise ValueError("refusing to overwrite existing files; use a new directory: " + ", ".join(conflicts))
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")
    # Parse what was actually saved rather than trusting construction alone.
    for name in ("source-single.srt", "target-single.srt", "bilingual-single.srt"):
        cues = parse_srt(output / name)
        if len(cues) != 1 or cues[0].start != 0 or cues[0].end != end:
            raise ValueError("saved generation input failed round-trip validation")
    if normalized(full_text(parse_srt(output / "source-single.srt"))) != normalized(source_text):
        raise ValueError("source text changed in output")
    if normalized(full_text(parse_srt(output / "target-single.srt"))) != normalized(target_text):
        raise ValueError("target text changed in output")
    return {"ok": True, "purpose": manifest["purpose"], "end_ms": end,
            "canonical_text_checked": canonical_checks, "files": list(files)}


def validate_pair(args):
    source, target = parse_srt(args.source_srt), parse_srt(args.target_srt)
    end = duration_ms(args.duration_seconds)
    if len(source) != len(target):
        raise ValueError(f"cue count mismatch: source={len(source)}, target={len(target)}")
    for index, (left, right) in enumerate(zip(source, target), 1):
        if (left.start, left.end) != (right.start, right.end):
            raise ValueError(f"cue {index}: source/target timecodes differ")
        if left.end > end:
            raise ValueError(f"cue {index}: end exceeds supplied video duration")
    for label, cues, original in (
        ("source", source, args.source_text),
        ("target", target, args.target_text),
    ):
        expected = normalized(read_text(original))
        if not expected:
            raise ValueError(f"{label}: canonical text is empty")
        if normalized(full_text(cues)) != expected:
            raise ValueError(f"{label}: SRT does not preserve the complete canonical text")
    return {
        "ok": True,
        "cues_per_track": len(source),
        "identical_timecodes": True,
        "canonical_text_preserved": True,
        "video_duration_ms": end,
        "final_cue_end_ms": source[-1].end,
        "audio_alignment_verified": False,
        "semantic_pairing_verified": False,
        "note": "Structure/text checks only; verify final audio timing and semantic pairing separately.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("prepare", help="build one-cue generation inputs; never final aligned subtitles")
    create.add_argument("--source-srt", required=True)
    create.add_argument("--target-srt", required=True)
    create.add_argument("--duration-seconds", required=True)
    create.add_argument("--output-dir", required=True)
    create.add_argument("--source-text", help="optional independent canonical source TXT for completeness check")
    create.add_argument("--target-text", help="optional independent canonical target TXT for completeness check")
    create.set_defaults(run=prepare)
    check = sub.add_parser("validate-pair", help="validate same-axis final SRT pair against canonical text")
    check.add_argument("--source-srt", required=True)
    check.add_argument("--target-srt", required=True)
    check.add_argument("--source-text", required=True)
    check.add_argument("--target-text", required=True)
    check.add_argument("--duration-seconds", required=True)
    check.set_defaults(run=validate_pair)
    args = parser.parse_args()
    try:
        report = args.run(args)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
