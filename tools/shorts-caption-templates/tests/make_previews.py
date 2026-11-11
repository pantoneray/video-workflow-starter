#!/usr/bin/env python3
"""After run_tests.sh: copy the rendered frames to previews/ with a small '示意' label."""
import os
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
f = ImageFont.truetype(os.path.join(ROOT, 'fonts', 'NotoSansSC-Medium.ttf'), 26)
names = {'A': 'A_threeband_card', 'B': 'B_word_highlight_quote', 'C': 'C_dialogue_switch', 'D': 'D_contemplative_phrase',
         'E_illustration': 'E_episode_title_card_illustration', 'E_footage': 'E_episode_title_card_footage', 'F': 'F_editorial_hook'}
os.makedirs(os.path.join(ROOT, 'previews'), exist_ok=True)
for k, v in names.items():
    im = Image.open(os.path.join(HERE, 'out', k + '.png')).convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    txt = f'{v}｜示意（合成画面＋测试字幕），非成片'
    w = d.textlength(txt, font=f); d.rounded_rectangle((24, 1856, 24 + w + 28, 1900), radius=10, fill=(0, 0, 0, 150))
    d.text((38, 1860), txt, font=f, fill=(255, 255, 255, 230))
    Image.alpha_composite(im, ov).convert('RGB').save(os.path.join(ROOT, 'previews', v + '.png'), optimize=True)
print('previews written')
