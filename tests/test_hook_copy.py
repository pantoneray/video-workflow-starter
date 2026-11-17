import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hook_copy import copy_proposal,review_round,sentence_ranges
from review_html import render
from review_protocol import validate_receipt
from translation_review import version_digest
from review_advance import continuation
from unittest.mock import Mock
from speech_plan import effective_count

class HookTests(unittest.TestCase):
 def test_source_mapping_timing_and_new_review(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'source.txt';text='不要忽略限定。 慈悲从日常开始！不是一次就能完成。';path.write_text(text)
   source={'file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'start':0,'end':len(text),'original_exact':text,'locator':'test line 1'}
   p=copy_proposal(source,1,characters_per_minute=180,rate_basis='explicit synthetic estimate, not measured')
   self.assertEqual(p['duration']['total_effective_characters'],effective_count(text))
   self.assertEqual(p['duration']['total_seconds_estimate'],round(60*effective_count(text)/180,3))
   self.assertEqual(p['A'],text);self.assertEqual(p['B'],' 慈悲从日常开始！不要忽略限定。不是一次就能完成。')
   self.assertFalse(p['packaging_preview_enabled']);self.assertTrue(p['requires_new_translation_review_if_B_selected'])
   for m in p['mapping']:
    self.assertEqual(p['A'][m['A_start']:m['A_end']],p['B'][m['B_start']:m['B_end']])
   current=review_round(p,task_id='test',item_id='01',batch='test',version='v2',round_id='test-T1-v2')
   page=render(current);self.assertIn('必须复核',page);self.assertNotIn('value="approved" selected',page)
   receipt={k:current[k] for k in ('schema_version','task_id','stage','language','version','round_id','entry')}
   item=current['items'][0]
   receipt.update(content_sha256=version_digest(current),submitted_at='2026-11-17T00:00:00Z',items=[{'id':'01','version':'v2','content_sha256':version_digest(item),'decision':'approved','selected_text':'B','comment':'synthetic review only','checks':{k:True for k in item['required_checks']}}])
   routed=validate_receipt(current,receipt,entry='local_html')
   self.assertEqual(routed['routes'][0]['next'],'T2')
   current_path=Path(d)/'round.json';current_path.write_text(json.dumps(current))
   result=continuation(current_path,Path(d)/'next')(receipt,routed)
   selected=json.loads(Path(result['items'][0]['selected_copy']).read_text())
   self.assertEqual(selected['production_text'],p['B'])
   self.assertFalse(selected['translation_approval_reusable'])
   self.assertEqual(result['items'][0]['state'],'awaiting_translation_and_independent_review')
   receipt_a=copy.deepcopy(receipt);receipt_a['items'][0]['selected_text']='A'
   routes_a=validate_receipt(current,receipt_a,entry='local_html')
   provider=Mock(side_effect=AssertionError('T1 must not call a model'))
   result_a=continuation(current_path,Path(d)/'next-a',provider=provider,model='test',allow_model=True)(receipt_a,routes_a)
   selected_a=json.loads(Path(result_a['items'][0]['selected_copy']).read_text())
   self.assertEqual(selected_a['production_text'],text);self.assertEqual(selected_a['hook_mode'],'none')
   self.assertFalse(selected_a['external_actions_authorized']);provider.assert_not_called()
   changed=copy.deepcopy(current);changed['items'][0]['content']['B']+='改稿'
   with self.assertRaises(ValueError):validate_receipt(changed,receipt,entry='local_html')
   same=copy_proposal(source,0,characters_per_minute=180,rate_basis='estimate')
   self.assertEqual(same['A'],same['B'])
   with self.assertRaises(ValueError):copy_proposal(source,-1,characters_per_minute=180,rate_basis='estimate')
   with self.assertRaises(ValueError):copy_proposal(source,1,characters_per_minute=float('nan'),rate_basis='estimate')
   with self.assertRaises(ValueError):copy_proposal(source,1,characters_per_minute=180,rate_basis='')
   path.write_text('changed')
   with self.assertRaises(ValueError):copy_proposal(source,1,characters_per_minute=180,rate_basis='estimate')
 def test_sentence_partition_keeps_every_character(self):
  for text in ['你好。\n再见。  ','他说：“不是。”后句！','Value 1.2 stays. Next sentence!','无句号也必须整体审核']:
   spans=sentence_ranges(text)
   self.assertEqual(''.join(text[a:b] for a,b in spans),text)

if __name__=='__main__':unittest.main()
