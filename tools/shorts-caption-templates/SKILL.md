---
name: shorts-caption-templates
description: Use when you need to turn a talk/footage or illustration clip plus word timestamps into a vertical 1080x1920 Short with one of 6 ready editing templates (caption style and position, layout, hook text, zoom rhythm, music level under the voice).
---

# Shorts caption templates (A–F)

Bundled copy: use the parent package’s `workflow.py captions` and read [the integration guide](../../references/caption-packaging.md). No repository access is needed. The parent workflow preserves approved case/punctuation, defaults to a static full-bleed frame, and does not use A or hide spoken words under F overlays. These task rules override the original style defaults below.

Six vertical-Shorts editing templates as JSON specs, plus one script that renders them with ffmpeg and libass. Every path below is relative to this skill's folder.

## 1. Prerequisites
- `ffmpeg` and `ffprobe` built with libass and libx264 (check with `ffmpeg -filters | grep -E "ass|zoompan|sidechaincompress"`).
- `python3` 3.9+ with Pillow (`pip install pillow`).
- Word timestamps from one of these:
  - `whisperX` (best word alignment): `whisperx clip.mp4 --model large-v3 --language <id|mn|zh|en…> --output_format json --output_dir words/`
  - `faster-whisper` with `word_timestamps=True`. Write it out as `{"segments":[{"start","end","text","words":[{"word","start","end"}]}]}`, the same layout whisperX uses.
  - Languages without a good alignment model (for example Mongolian): transcribe, then fix the timing by hand. Always proofread the words.
- Fonts are in `fonts/`: static Montserrat and Noto instances, all OFL. They cover Latin, Cyrillic (incl. Ө Ү) and CJK. Do not swap in paid fonts.

## 2. Pick a template (by layout and rhythm, not by content type)
Any template works for live-action, b-roll or illustration. Pick by how the frame should look and how fast it should move.

| ID | Spec | Layout | Rhythm | Captions | Music |
|---|---|---|---|---|---|
| A | `specs/A_threeband_card.json` | 16:9 source kept whole in a middle band (y 660–1268) over a blurred copy of itself. Title and nameplate on top. | One shot, no cuts | Phrase captions, center y 1390 | Optional, −18 dB under voice |
| B | `specs/B_word_highlight_quote.json` | Full-bleed 9:16 | Changes every ~1.5–3 s (punch-in 100↔112%) | Word-by-word highlight with pop, center y 1440 | −18 dB |
| C | `specs/C_dialogue_switch.json` | Full-bleed, serif nameplate lower-left | Shots of 3.5–6 s, punch-in 108% | Sentence captions, center y 1500 | None |
| D | `specs/D_contemplative_phrase.json` | Full-bleed | Slow, 6–13 s, punch-in 115% | Lowercase serif; upcoming words grey, spoken words white; center y 1440 | −22 dB |
| E | `specs/E_episode_title_card.json` | Episode tag + title on top. Background is either art (`illustration`) or live footage (`footage`). | Slow push-in (Ken Burns, 1.00→1.05) | Gold word fill, center y 1480 | −20 dB |
| F | `specs/F_editorial_hook.json` | Hook module: big type in the lower band for the first ~3 s, then captions | Fast, 2–3.5 s | Small boxed captions, center y 1545 | −18 dB |

Common combinations: F → A for horizontal talks, F → B for close-ups, C for Q&A, D for slow passages, E for any numbered series.

## 3. Render
```bash
python3 scripts/apply_template.py --template specs/<ID>.json \
  --video input.mp4 --words words/input.json --lang <id|mn|zh|en> --out out/<name>.mp4 \
  [--music royalty_free.mp3] [--preview 1.5]
```
Template-specific flags:
- A: `--title "…" --title-hl "WORD1,WORD2" --name "Speaker Name"`
- C: `--name "Speaker Name" --name-sub "Role" --name-in 4`
- E: `--kicker "• EP 1 •" --title "…" --background-mode illustration|footage`
  - `footage` shifts the video down 220 px under a shaded title band, so the title sits above the head.
- F: `--overlay "BIG|small|BIG" --overlay-dur 3`. Captions wait until the big type is gone.
- Other flags:
  - `--emph "w1,w2"` keeps extra words highlighted (B).
  - `--ass-only` writes only the subtitle file.
  - `--preview <sec>` also writes `out/<name>.png`.

What the script does:
1. Crops or lays out the frame.
2. Adds a punch-in or Ken Burns zoom.
3. Burns in the captions.
4. Ducks the music under the voice with sidechain compression.
5. Normalizes loudness to −14 LUFS / −1 dBTP.

Output is 1080×1920, 30 fps, H.264 + AAC. Style headers for editing in Aegisub are in `ass/<ID>_<lang>.ass`. To change a template, edit `scripts/make_specs.py` and run it again; it rewrites `specs/`.

## 4. Hard rules
1. **Captions go in the lower band.** Caption centers stay within y 1300–1560 and never cover a face (the face zone in a full-bleed medium shot is about y 420–1150). F's big hook words also go in the lower band. The script clamps out-of-band values and prints `WARNING`.
2. **Captions are horizontally centered.** The main spoken caption is always anchored at the horizontal center, x = 540 (`\an5\pos(540,y)`). Do not shift it left or right to make room for the right-side buttons or for any other reason. The safe area is handled by the equal 140 px left and right margins, which keep text between x 140 and 940; if a line is too long, wrap it or shorten the chunk instead. This applies even when you only reuse the styles and generate caption events with your own script. Titles, kickers and F's big hook words are centered the same way; only C's nameplate sits lower-left by design.
3. **Close-up exception.** If the chin falls below about y 1250 after the 9:16 crop, use A, or scale the footage down and shift it up (uniform scale only) before applying the template.
4. **Portraits.** Keep the whole head visible: never crop the top of the head and never put a title over it. Never stretch, reshape or retouch a person.
5. **Music.** Use only royalty-free or properly licensed music, at the template's level under the voice (−18 to −22 dB, none for C).
6. **Reference material.** Never reuse other creators' footage, music, illustrations or paid fonts. The references only informed the style.
7. **Titles and captions.**
   - No misleading or exaggerated titles. Don't change the speaker's meaning, and don't drop qualifiers ("maybe", "sometimes").
   - Cite sources for quotes and stories.
   - Have a native speaker check translations.
   - Trailing commas, periods, colons and semicolons (`, . ; : ，。、；：…`) are dropped from the end of each caption chunk so lines stay visually centered; `?` and `!` are kept. The script does this automatically.
8. **Stay local.** Output stays on the local machine. Do not upload or publish unless the owner explicitly asks.

## 5. Verify before handing over
- [ ] Extract 2–3 frames per output (`ffmpeg -ss <t> -i out.mp4 -frames:v 1 f.png`, including one while the hook or title is on screen) and **look at them**:
  - face uncovered;
  - whole head visible;
  - captions inside the lower band;
  - captions horizontally centered: the left and right gaps around each caption line differ by no more than about 10 px;
  - nothing under the right-side buttons (x > 940) or the bottom UI (y > 1620).
- [ ] Fonts render correctly for the language: no tofu boxes; Ө/Ү and Chinese characters are present.
- [ ] `ffmpeg -i out.mp4 -af ebur128 -f null -` reports about −14 LUFS; music is audible but clearly under the voice.
- [ ] Caption text matches the transcript word for word; the title matches what is actually said.
- [ ] Run `bash tests/run_tests.sh` after changing the script or specs. It must end with `ALL TESTS PASSED`.
