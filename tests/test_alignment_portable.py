import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'faithful-audio-align' / 'scripts'))
import align


class IntegrityTests(unittest.TestCase):
    def test_multilingual_round_trip_and_spacing(self):
        for source in ['蒙古语原文，完整保留。\n下一句！', 'Сайн байна уу, дэлхий.', 'صباح الخير، شكراً لحضوركم.']:
            pieces = align.split_clauses(source)
            self.assertEqual(align.compact(''.join(pieces)), align.compact(source))
            if ' ' in source:
                self.assertIn(' ', ''.join(pieces))

    def test_decimal_not_split(self):
        self.assertEqual(align.split_clauses('价格3.14，数量1,000。'), ['价格3.14，', '数量1,000。'])

    def test_model_omission_rejected(self):
        raw = {'segments': [{'words': [{'word': '甲', 'start': 1, 'end': 2}]}]}
        with self.assertRaises(ValueError):
            align.map_chars(raw, '甲乙')

    def test_absolute_local_offset(self):
        raw = {'segments': [{'words': [{'word': '甲。', 'start': 1.1, 'end': 2.2}]}]}
        mapped = align.map_chars(raw, '甲。', offset=60)
        self.assertAlmostEqual(mapped[0]['start'], 61.1)
        self.assertAlmostEqual(mapped[-1]['end'], 62.2)

    def test_jump_is_flagged_without_fabrication(self):
        chars = [dict(char='甲', start=1, end=2), dict(char='乙', start=20, end=21)]
        for c in chars:
            c['probability'] = 0.8
        cues, issues = align.build_cues('甲乙', chars, 30)
        self.assertTrue(issues)
        self.assertEqual(cues[0]['end'], 21)

    def test_overlap_is_fatal(self):
        raw = {'segments': [{'words': [{'word': '甲，', 'start': 1, 'end': 3},
                                       {'word': '乙。', 'start': 2, 'end': 4}]}]}
        cues, issues = align.build_cues('甲，乙。', align.map_chars(raw, '甲，乙。'), 10)
        self.assertTrue(any(x['fatal'] for x in issues))

    def test_anchors_require_unambiguous_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'anchors.json'
            path.write_text(json.dumps([dict(text='甲', start=0, end=1)]), encoding='utf-8')
            with self.assertRaises(ValueError):
                align.validate_anchors(path, '甲甲', 4)
            path.write_text(json.dumps([dict(text='甲', start=0, end=1, offset=1)]), encoding='utf-8')
            self.assertEqual(align.validate_anchors(path, '甲甲', 4)[0]['offset'], 1)

    def test_atomic_unicode_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '字幕 蒙语.srt'
            text = align.render_srt([dict(index=1, start=61.123, end=62.456, text='你好。')])
            align.atomic_text(path, text)
            self.assertEqual(path.read_text(encoding='utf-8'), text)
            self.assertIn('00:01:01,123 --> 00:01:02,456', text)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, source, output = root / 'song.wav', root / 'source.txt', root / 'song.srt'
            audio.write_bytes(b'test placeholder')
            source.write_text('原文。', encoding='utf-8')
            output.write_text('已有字幕', encoding='utf-8')
            args = align.parser().parse_args([str(audio), str(source)])
            with self.assertRaises(ValueError):
                align.run(args)
            self.assertEqual(output.read_text(encoding='utf-8'), '已有字幕')

    def test_internal_reverse_is_fatal(self):
        chars = [dict(char='甲', start=2, end=3, probability=0.9),
                 dict(char='乙', start=1, end=2, probability=0.9)]
        _, issues = align.build_cues('甲乙', chars, 10)
        self.assertTrue(any(x['fatal'] for x in issues))


if __name__ == '__main__':
    unittest.main()
