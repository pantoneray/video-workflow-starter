import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from select_candidates import ACTION_CHECKS, choose, clean_windows
from scan_long import run
from slice import sha256, probe_video


def approved(report, candidates):
    return {'candidates_sha256': sha256(report), 'reviews': [
        {'candidate_id': c['id'], 'start': c['start'], 'end': c['end'],
         'watched_full_candidate': True, 'existing_visual_rules_pass': True,
         'reviewer': 'offline fixture', 'notes': 'Synthetic annotations, not real gesture recognition',
         'decision': 'approve', 'actions': {k: 'acceptable' for k in ACTION_CHECKS}} for c in candidates]}


class FullScanActionsTests(unittest.TestCase):
    def test_multiple_windows_and_tail(self):
        windows = clean_windows(137, [], 30, 45)
        self.assertEqual(windows[:3], [(0,45), (45,90), (90,135)])
        self.assertEqual(windows[-1][1], 137)
        self.assertTrue(all(30 <= b-a <= 45 for a,b in windows))

    def test_all_action_checks_gate_selection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); report=p/'candidates.json'; review=p/'review.json'; cuts=p/'cuts.json'
            candidates=[{'id':1,'start':0,'end':35},{'id':2,'start':35,'end':70}]
            report.write_text(json.dumps({'source':'fixture.mp4','candidates':candidates}))
            valid=approved(report,candidates)
            args=SimpleNamespace(candidates=str(report), candidate_id=[1,2], visual_reviewed=True,
                                 review_file=str(review),out=str(cuts))
            for action in ACTION_CHECKS:
                for verdict in ('excessive','frequent','uncertain','unreviewed'):
                    changed=copy.deepcopy(valid); changed['reviews'][1]['actions'][action]=verdict
                    review.write_text(json.dumps(changed))
                    with self.assertRaises(ValueError): choose(args)
                    self.assertFalse(cuts.exists())
            changed=copy.deepcopy(valid); changed['reviews'][0]['watched_full_candidate']=False
            review.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): choose(args)
            review.write_text(json.dumps(valid)); choose(args)
            self.assertEqual(len(json.loads(cuts.read_text())),2)

    def test_real_full_video_and_three_slices_beyond_ten_minutes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); source=p/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'testsrc2=size=160x120:rate=2:duration=650','-c:v','libx264',
                            '-preset','ultrafast',str(source)],check=True,timeout=90)
            original=sha256(source)
            rules=json.loads((ROOT/'config/selection-rules.example.json').read_text())
            rules.update(min_short_side=100,scene_threshold=0.99)
            rules_path=p/'rules.json';rules_path.write_text(json.dumps(rules))
            subprocess.run([sys.executable,str(ROOT/'scripts/select_candidates.py'),'scan',
                            '--input',str(source),'--rules',str(rules_path),'--out',str(p/'single-scan')],
                           check=True,capture_output=True,timeout=90)
            single=json.loads((p/'single-scan/candidates.json').read_text())
            self.assertTrue(single['full_source_covered'])
            self.assertEqual(single['scan_seconds'],650)
            self.assertGreater(len(single['candidates']),6)
            report=run(source,rules_path,p/'scan')
            self.assertTrue(report['full_source_covered'])
            self.assertEqual(report['coverage_seconds'],650)
            self.assertGreater(len(report['candidates']),6)
            self.assertEqual(len({c['id'] for c in report['candidates']}),len(report['candidates']))
            late=next(c for c in reversed(report['candidates']) if c['start']>=600)
            selected=report['candidates'][:2]+[late]
            report_path=p/'scan/coverage.json';review=p/'review.json';cuts=p/'cuts.json'
            review.write_text(json.dumps(approved(report_path,selected)))
            choose(SimpleNamespace(candidates=str(report_path),candidate_id=[c['id'] for c in selected],
                                   visual_reviewed=True,review_file=str(review),out=str(cuts)))
            subprocess.run([sys.executable,str(ROOT/'scripts/slice.py'),'--input',str(source),
                            '--cuts',str(cuts),'--out',str(p/'output')],check=True,capture_output=True,timeout=90)
            manifest=json.loads((p/'output/manifest.json').read_text())
            self.assertEqual(len(manifest['segments']),3)
            for segment in manifest['segments']:
                self.assertTrue(30<=probe_video(segment['file'])[0]<=45)
                subprocess.run(['ffmpeg','-v','error','-i',segment['file'],'-f','null','-'],
                               check=True,capture_output=True,timeout=60)
            self.assertEqual(sha256(source),original)
            resumed=run(source,rules_path,p/'scan')
            self.assertEqual(resumed['segments_resumed'],len(report['covered_intervals']))
            self.assertEqual(resumed['candidates'],report['candidates'])


if __name__=='__main__':unittest.main()
