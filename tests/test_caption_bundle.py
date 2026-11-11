import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from caption_templates import render, validate_words, renderer_ffmpeg, digest
from translation_review import create_item


class CaptionBundleTests(unittest.TestCase):
    def test_existing_draft_is_reviewed_independently_without_retranslation(self):
        calls = []
        def call(stage, prompt, model):
            calls.append((stage, prompt))
            field = {'independent_translation': 'translation', 'backtranslation': 'backtranslation',
                     'independent_review': 'review'}[stage]
            return {'items': [{'id': '1', field: 'Independent result'}]}
        result = create_item({'original_exact': 'Original passage', 'file': 'book.txt', 'locator': 'line 1'},
                             'en', {'review_model': 'review', 'backtranslation_model': 'back'},
                             draft='Keep My Draft.', draft_author='Codex', stage_call=call)
        self.assertEqual(result['translation'], 'Keep My Draft.')
        self.assertEqual(result['models']['translation'], 'Codex')
        self.assertEqual([x[0] for x in calls], ['independent_translation', 'backtranslation', 'independent_review'])
        self.assertNotIn('Keep My Draft.', calls[0][1])
        self.assertNotIn('Original passage', calls[1][1])

    def test_words_reject_changes_and_invalid_timing(self):
        data = {'segments': [{'words': [{'word': 'Keep,', 'start': .1, 'end': .8}]}]}
        validate_words(data, 'Keep,', 2)
        for changed in ('keep,', 'Keep', 'Changed,'):
            with self.assertRaises(ValueError):
                validate_words(data, changed, 2)
        data['segments'][0]['words'][0]['end'] = float('nan')
        with self.assertRaises(ValueError):
            validate_words(data, 'Keep,', 2)

    def test_real_render_from_bundled_files_preserves_inputs_and_text(self):
        try:
            executable = renderer_ffmpeg()
        except ValueError:
            self.skipTest('Optional caption FFmpeg dependency is not installed')
        with tempfile.TemporaryDirectory(prefix='captions space-') as temporary:
            root = Path(temporary)
            video = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=360x640:r=30:d=2',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264',
                            '-c:a', 'aac', '-shortest', str(video)], check=True, timeout=60)
            before = digest(video)
            words = root / 'words.json'
            words.write_text(json.dumps({'segments': [{'words': [
                {'word': 'Keep', 'start': .1, 'end': .5},
                {'word': 'This,', 'start': .5, 'end': 1.0},
                {'word': 'Text.', 'start': 1.1, 'end': 1.8}]}]}))
            approved = root / 'approved.txt'
            approved.write_text('Keep This, Text.')
            out = root / "user's output"
            receipt = render(video, words, approved, out, language='en', ffmpeg=executable)
            self.assertEqual(receipt['state'], 'technical_pass_visual_review_pending')
            self.assertEqual(digest(video), before)
            ass = (out / 'final.ass').read_text()
            events = [line for line in ass.splitlines() if line.startswith('Dialogue:') and ',Cap,' in line]
            self.assertTrue(events)
            self.assertTrue(all('\\an5\\pos(540,' in line for line in events))
            visible = re.sub(r'\{[^}]*\}', '', '\n'.join(events))
            for word in ('Keep', 'This,', 'Text.'):
                self.assertIn(word, visible)
            self.assertTrue((out / 'final.png').is_file())
            with self.assertRaises(FileExistsError):
                render(video, words, approved, out, language='en', ffmpeg=executable)
            with self.assertRaises(ValueError):
                render(video, words, approved, root / 'a', template='A', language='en', ffmpeg=executable)


if __name__ == '__main__':
    unittest.main()
