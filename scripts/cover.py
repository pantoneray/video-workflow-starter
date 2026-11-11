#!/usr/bin/env python3
"""Make a simple cover from an authorized background without changing faces."""
import argparse
import hashlib
import json
from pathlib import Path


def build(background, title, font_path, out, width=1080, height=1920):
    from PIL import Image, ImageDraw, ImageFont
    background, font_path, out = Path(background), Path(font_path), Path(out)
    if not background.is_file() or not font_path.is_file() or out.exists():
        raise ValueError("背景/字体不存在，或输出已存在")
    if not title.strip() or len(title) > 100:
        raise ValueError("封面文字为空或过长")
    if width < 320 or height < 320:
        raise ValueError("封面规格太小")
    image = Image.open(background).convert("RGB")
    image.thumbnail((width, height))
    canvas = Image.new("RGB", (width, height), "#17191c")
    canvas.paste(image, ((width-image.width)//2, (height-image.height)//2))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    band_top = int(height * .66)
    draw.rectangle((0, band_top, width, height), fill=(0, 0, 0, 190))
    font_size = max(24, round(width * .055))
    font = ImageFont.truetype(str(font_path), font_size)
    max_width = int(width * .82)
    lines, current = [], ""
    for character in title:
        trial = current + character
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = character
        else:
            current = trial
    if current:
        lines.append(current)
    if len(lines) > 4:
        raise ValueError("封面文字超过 4 行；请精简")
    y = band_top + int((height-band_top-len(lines)*font_size*1.35)/2)
    for line in lines:
        x = (width - draw.textlength(line, font=font)) / 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=2, stroke_fill="#111111")
        y += int(font_size * 1.35)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=94)
    receipt = {"cover": str(out.resolve()), "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
               "background": str(background.resolve()), "background_sha256": hashlib.sha256(background.read_bytes()).hexdigest(),
               "title": title, "size": [width, height], "face_editing": False, "human_review": "required"}
    receipt_path = out.with_suffix(out.suffix + ".json")
    with receipt_path.open("x", encoding="utf-8") as item:
        json.dump(receipt, item, ensure_ascii=False, indent=2)
        item.write("\n")
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--background", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--font", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    a = p.parse_args()
    print(json.dumps(build(a.background, a.title, a.font, a.out, a.width, a.height), ensure_ascii=False))


if __name__ == "__main__":
    main()
