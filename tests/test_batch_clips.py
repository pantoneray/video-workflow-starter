import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import batch_clips as b
class BatchTests(unittest.TestCase):
 def test_order_is_stable_with_parallel_scan(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);src=p/'src';src.mkdir()
   for name in ['low.mp4','high.mp4']:(src/name).write_bytes(b'x')
   def probe(path):return (80,1920,1080) if path.name=='high.mp4' else (80,1280,720)
   def scan(*args):return {'candidates':[{},{}]}
   with patch.object(b,'probe_video',side_effect=probe),patch.object(b,'run',side_effect=scan):
    for workers in (1,2):
     result=b.scan_folder(src,p/str(workers),'rules',3,workers)
     self.assertTrue(result['sources'][0]['source'].endswith('high.mp4'))
     self.assertEqual(len(result['sources']),2)
 def test_quota_and_shortfall(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);reports=[str(p/'a.json'),str(p/'b.json')]
   batch=p/'batch.json';batch.write_text(json.dumps({'count':3,'per_video':1,'sources':[{'source':'a.mp4','report':reports[0]},{'source':'b.mp4','report':reports[1]}]}))
   selections=p/'selected.json';selections.write_text(json.dumps([{'report':r,'candidate_ids':[1,2],'review_file':'review.json'} for r in reports]))
   def choose(args):Path(args.out).write_text(json.dumps([{'start':0,'end':35},{'start':40,'end':75}]))
   with patch.object(b,'choose',side_effect=choose),patch.object(b.subprocess,'run') as run:
    result=b.export(batch,selections,p/'out')
    self.assertEqual(result['exported'],2);self.assertEqual(result['shortfall'],1);self.assertEqual(run.call_count,2)
if __name__=='__main__':unittest.main()
