import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import importlib.util
import hashlib

ROOT = Path(__file__).resolve().parents[1]


class AutoSelectTest(unittest.TestCase):
    def test_scene_boundary_blocks_long_candidate(self):
        sys.path.insert(0, str(ROOT/'scripts'))
        spec = importlib.util.spec_from_file_location('select_candidates', ROOT/'scripts/select_candidates.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual(module.clean_windows(40, [(19.3, 20.7)], 30, 45, 6), [])

    def test_real_jump_cut_yields_no_30_second_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source = p/'jump.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                            'testsrc2=size=160x120:rate=5:duration=40','-vf',
                            "drawbox=color=red:t=fill:enable='gte(t,20)'",
                            '-c:v','libx264','-preset','ultrafast',str(source)], check=True, timeout=60)
            rules = json.loads((ROOT/'config/selection-rules.example.json').read_text())
            rules['min_short_side'] = 100
            rule_path = p/'rules.json'; rule_path.write_text(json.dumps(rules))
            subprocess.run([sys.executable,str(ROOT/'scripts/select_candidates.py'),'scan','--input',str(source),
                            '--rules',str(rule_path),'--out',str(p/'scan'),'--scan-seconds','40'],
                           check=True, capture_output=True, timeout=60)
            report = json.loads((p/'scan/candidates.json').read_text())
            self.assertGreaterEqual(report['detected_scene_cuts'], 1)
            self.assertEqual(report['candidates'], [])

    def test_agent_candidate_to_preserved_slice(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source = p / 'source.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                            'testsrc2=size=160x120:rate=5:duration=34','-c:v','libx264',
                            '-preset','ultrafast',str(source)], check=True, timeout=60)
            original = source.read_bytes()
            rules = json.loads((ROOT/'config/selection-rules.example.json').read_text())
            rules.update(min_short_side=100, scene_threshold=0.99)
            rule_path = p/'rules.json'; rule_path.write_text(json.dumps(rules))
            script = ROOT/'scripts/select_candidates.py'
            subprocess.run([sys.executable,str(script),'scan','--input',str(source),'--rules',str(rule_path),
                            '--out',str(p/'scan'),'--scan-seconds','34'], check=True, capture_output=True, timeout=60)
            report = json.loads((p/'scan/candidates.json').read_text())
            candidate = report['candidates'][0]
            self.assertGreaterEqual(candidate['duration'], 30)
            self.assertLessEqual(candidate['duration'], 45)
            self.assertEqual(len(candidate['preview_frames']), 5)
            denied = subprocess.run([sys.executable,str(script),'choose','--candidates',str(p/'scan/candidates.json'),
                                     '--candidate-id','1','--out',str(p/'cuts.json')], capture_output=True)
            self.assertNotEqual(denied.returncode, 0)
            subprocess.run([sys.executable,str(script),'review','--candidates',str(p/'scan/candidates.json'),
                            '--candidate-id','1','--out',str(p/'review')], check=True, capture_output=True)
            review_path = p/'review/review.json'
            review = json.loads(review_path.read_text())
            entry = review['reviews'][0]
            entry.update(watched_full_candidate=True, existing_visual_rules_pass=True,
                         decision='approve', reviewer='offline fixture', notes='Synthetic sample; no claim of real human gesture recognition')
            entry['actions'] = {k: 'acceptable' for k in entry['actions']}
            review_path.write_text(json.dumps(review))
            subprocess.run([sys.executable,str(script),'choose','--candidates',str(p/'scan/candidates.json'),
                            '--candidate-id','1','--review-file',str(review_path),'--visual-reviewed','--out',str(p/'cuts.json')],
                           check=True, capture_output=True)
            subprocess.run([sys.executable,str(ROOT/'scripts/slice.py'),'--input',str(source),
                            '--cuts',str(p/'cuts.json'),'--out',str(p/'out')], check=True, capture_output=True)
            output = p/'out/segments/seg-01-selected.mp4'
            subprocess.run([sys.executable,str(ROOT/'scripts/check_output.py'),'--input',str(output),
                            '--out',str(p/'qc.json')], check=True, capture_output=True)
            self.assertEqual(json.loads((p/'qc.json').read_text())['decode'], 'PASS')
            self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__': unittest.main()
