import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from notion_review_adapter import from_blocks
from review_protocol import validate_round


class NotionAdapterTest(unittest.TestCase):
    def setUp(self):
        self.current={'schema_version':1,'task_id':'test','stage':'T3','language':'id','version':'v1',
            'round_id':'r1','batch':'test','entry':'notion','items':[{'id':'01','version':'v1',
            'content':{'title':'test'},'required_checks':['meaning'],'approval_blockers':[]}]}
        binding=validate_round(self.current)
        def block(ident,kind,text='',checked=False):
            return {'id':ident,'type':kind,kind:{'rich_text':[{'plain_text':text}],'checked':checked},
                'last_edited_time':'2026-11-17T00:00:00Z','last_edited_by':{'id':'reviewer'}}
        self.blocks=[block('binding','code',binding),block('submit','to_do',checked=True),
            block('content','code',json.dumps({'title':'test'})),block('yes','to_do',checked=True),
            block('no','to_do'),block('comment','paragraph'),block('check','to_do',checked=True)]
        self.registration={'page_id':'test-page','round_sha256':binding,'reviewer_ids':['reviewer'],
            'binding_block':'binding','submit_block':'submit','items':{'01':{'content_block':'content',
            'approved_block':'yes','rework_block':'no','comment_block':'comment','checks':{'meaning':'check'}}}}
    def test_explicit_approval_and_stable_receipt(self):
        result=from_blocks(self.current,self.registration,self.blocks)
        self.assertEqual(result['receipt']['items'][0]['decision'],'approved')
        self.assertFalse(result['route']['external_actions_authorized'])
        self.assertEqual(result,from_blocks(self.current,self.registration,self.blocks))
        self.blocks[1]['to_do']['checked']=False
        self.assertEqual(from_blocks(self.current,self.registration,self.blocks)['state'],'no_change')
    def test_reject_unchecked_conflict_wrong_actor_late_edit_content_change(self):
        for index,modify in [
            (6,lambda b:b['to_do'].update(checked=False)),
            (4,lambda b:b['to_do'].update(checked=True)),
            (1,lambda b:b['last_edited_by'].update(id='other')),
            (5,lambda b:b.update(last_edited_time='2026-11-17T00:00:01Z')),
            (2,lambda b:b['code'].update(rich_text=[{'plain_text':'{"title":"changed"}'}]))]:
            blocks=copy.deepcopy(self.blocks);modify(blocks[index])
            with self.assertRaises(ValueError):from_blocks(self.current,self.registration,blocks)
        current=copy.deepcopy(self.current);current['entry']='local_html'
        with self.assertRaises(ValueError):from_blocks(current,self.registration,self.blocks)


if __name__=='__main__':unittest.main()
