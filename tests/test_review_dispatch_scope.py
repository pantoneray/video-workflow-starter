import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from review_dispatch import drain
from review_receipts import Receipts
from review_protocol import validate_round
import test_review_protocol


class DispatchScopeTest(unittest.TestCase):
    def test_one_round_does_not_claim_other_tasks_or_stale_content(self):
        fixture=test_review_protocol.ReviewProtocolTest();fixture.setUp()
        a=copy.deepcopy(fixture.round);ra=copy.deepcopy(fixture.receipt)
        b=copy.deepcopy(a);rb=copy.deepcopy(ra)
        b['task_id']=rb['task_id']='another-task'
        rb['content_sha256']=validate_round(b)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rp=root/'round.json';rp.write_text(json.dumps(a))
            store=Receipts(root/'store')
            ida=store.receive(a,ra,entry='local_html',page='<html>A</html>')['id']
            idb=store.receive(b,rb,entry='local_html',page='<html>B</html>')['id'];store.close()
            calls=[]
            def handler(receipt,route):
                calls.append(receipt['task_id']);return {'state':'local_test_only'}
            with patch('review_dispatch.continuation',return_value=handler):
                result=drain(root/'store',rp,root/'output')
                self.assertEqual(len(result['results']),1);self.assertEqual(calls,[a['task_id']])
                self.assertEqual(drain(root/'store',rp,root/'output')['state'],'no_change')
                b['version']='changed-without-new-round';rp.write_text(json.dumps(b))
                stale=drain(root/'store',rp,root/'output')
                self.assertEqual(stale['state'],'no_change');self.assertEqual(stale['stale_current_round_receipts'],[idb])
            store=Receipts(root/'store')
            self.assertEqual(store.status(ida)['state'],'completed')
            self.assertEqual(store.status(idb)['state'],'received');store.close()
            self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
