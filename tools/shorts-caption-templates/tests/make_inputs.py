#!/usr/bin/env python3
"""Generate synthetic test inputs (no real people, no third-party media):
- a 16:9 still 'speaker' silhouette clip, an illustration-style clip, a sine music bed,
- dummy word-timestamp JSON (whisperX format) in id / mn / zh."""
import json, os, subprocess, sys
from PIL import Image, ImageDraw
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)

def still(img, name, secs=9):
    png = os.path.join(OUT, name + '.png'); img.save(png)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', png, '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
                    '-t', str(secs), '-vf', 'format=yuv420p', '-r', '30', '-c:v', 'libx264', '-c:a', 'aac', '-shortest',
                    os.path.join(OUT, name + '.mp4')], check=True)

# speaker silhouette, 1920x1080 (head ~y200-460, so after 9:16 cover-crop the face sits in the upper half)
W, H = 1920, 1080
im = Image.new('RGB', (W, H)); d = ImageDraw.Draw(im)
for y in range(H): d.line((0, y, W, y), fill=(int(30 + 40 * y / H), int(34 + 30 * y / H), int(44 + 20 * y / H)))
d.ellipse((835, 190, 1085, 470), fill=(176, 150, 128))                  # head
d.polygon([(700, 1080), (760, 600), (960, 520), (1160, 600), (1220, 1080)], fill=(120, 40, 36))  # body
d.rectangle((930, 460, 990, 540), fill=(160, 134, 114))                 # neck
still(im, 'speaker_16x9')

# illustration-style background, 1080x1920
W, H = 1080, 1920
im = Image.new('RGB', (W, H)); d = ImageDraw.Draw(im)
for y in range(H): d.line((0, y, W, y), fill=(int(40 + 150 * y / H), int(50 + 90 * y / H), int(90 + 40 * y / H)))
d.ellipse((640, 520, 860, 740), fill=(246, 214, 140))
d.polygon([(0, 1250), (300, 820), (560, 1150), (820, 760), (1080, 1100), (1080, 1920), (0, 1920)], fill=(70, 62, 90))
d.polygon([(0, 1450), (380, 1150), (760, 1400), (1080, 1220), (1080, 1920), (0, 1920)], fill=(48, 44, 64))
still(im, 'illustration_9x16')

subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=f=220:d=12', '-f', 'lavfi', '-i', 'sine=f=330:d=12',
                '-filter_complex', 'amix=inputs=2,volume=0.3', os.path.join(OUT, 'music_sine.wav')], check=True)

def words(tokens, fn, t0=0.3, step=0.32):
    ws = []; t = t0
    for w in tokens:
        ws.append({'word': w, 'start': round(t, 2), 'end': round(t + step - 0.04, 2)}); t += step
    json.dump({'segments': [{'start': ws[0]['start'], 'end': ws[-1]['end'], 'text': ' '.join(tokens), 'words': ws}]},
              open(os.path.join(OUT, fn), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
words('Ini hanya teks contoh untuk menguji gaya subtitle. Bukan kutipan siapa pun.'.split(), 'words_id.json')
words('Энэ бол хадмал бичгийн загварыг шалгах жишээ текст. Хэний ч үг биш.'.split(), 'words_mn.json')
words(['这是', '字幕', '样式', '测试', '文本，', '不是', '任何', '人的', '原话。'], 'words_zh.json')
print('inputs ready in', OUT)
