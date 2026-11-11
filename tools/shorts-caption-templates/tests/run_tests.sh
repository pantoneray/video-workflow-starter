#!/usr/bin/env bash
# Renders every template (E in both background modes) on synthetic inputs and checks the outputs.
# Usage: bash tests/run_tests.sh   (run from anywhere; paths are relative to this file)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; ROOT="$(dirname "$HERE")"; OUT="$HERE/out"
S="$ROOT/scripts/apply_template.py"; T="$ROOT/specs"
python3 "$HERE/make_inputs.py" "$OUT"
cd "$OUT"
run(){ echo "== $*"; python3 "$S" "$@" | tee -a render.log | grep -E "rendered|WARNING" || true; }
: > render.log
run --template "$T/A_threeband_card.json"       --video speaker_16x9.mp4 --words words_mn.json --lang mn --out A.mp4 --title "TEST TITLE ӨГӨХ" --title-hl "ӨГӨХ" --name "Speaker Name" --music music_sine.wav --preview 2.1
run --template "$T/B_word_highlight_quote.json" --video speaker_16x9.mp4 --words words_id.json --lang id --out B.mp4 --music music_sine.wav --preview 0.75
run --template "$T/C_dialogue_switch.json"      --video speaker_16x9.mp4 --words words_zh.json --lang zh --out C.mp4 --name "Speaker Name" --name-sub "Title" --name-in 0.5 --preview 1.5
run --template "$T/D_contemplative_phrase.json" --video speaker_16x9.mp4 --words words_id.json --lang id --out D.mp4 --music music_sine.wav --preview 0.9
run --template "$T/E_episode_title_card.json"   --video illustration_9x16.mp4 --words words_mn.json --lang mn --out E_illustration.mp4 --kicker "• 1-р хэсэг •" --title "Туршилт" --music music_sine.wav --preview 1.3
run --template "$T/E_episode_title_card.json"   --background-mode footage --video speaker_16x9.mp4 --words words_mn.json --lang mn --out E_footage.mp4 --kicker "• EP 1 •" --title "Test Title" --music music_sine.wav --preview 1.3
run --template "$T/F_editorial_hook.json"       --video speaker_16x9.mp4 --words words_id.json --lang id --out F.mp4 --overlay "BIG|small|WORDS" --preview 1.3
fail=0
for f in A B C D E_illustration E_footage F; do
  if [[ ! -s "$f.mp4" || ! -s "$f.png" ]]; then echo "FAIL $f: missing output"; fail=1; continue; fi
  wh=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$f.mp4")
  [[ "$wh" == "1080,1920" ]] || { echo "FAIL $f: size $wh"; fail=1; }
  lufs=$(ffmpeg -nostats -i "$f.mp4" -af ebur128 -f null - 2>&1 | awk '/I:/{v=$2} END{print v}')
  echo "ok   $f  ${wh}  ${lufs} LUFS"
done
# v1.4: every main caption event must be anchored at the horizontal center (x=540)
for f in A B C D E_illustration E_footage F; do
  bad=$(grep ',Cap,' "$f.ass" | grep -vc 'an5\\pos(540,' || true)
  [[ "$bad" == 0 ]] || { echo "FAIL $f: $bad caption events not centered at x=540"; fail=1; }
done
if grep -q WARNING render.log; then echo "FAIL: caption band warnings"; fail=1; fi
[[ $fail == 0 ]] && echo "ALL TESTS PASSED" || { echo "TESTS FAILED"; exit 1; }
