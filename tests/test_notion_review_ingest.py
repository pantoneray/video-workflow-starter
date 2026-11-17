import copy,json,sys,tempfile,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from notion_review_ingest import ingest
from review_receipts import Receipts
import test_notion_review_adapter


class IngestTest(unittest.TestCase):
    def setUp(self):
        f=test_notion_review_adapter.NotionAdapterTest();f.setUp();self.current=f.current
        ids={b['id']:str(uuid.uuid4()) for b in f.blocks};self.page=str(uuid.uuid4())
        self.registration=json.loads(json.dumps(f.registration),object_hook=lambda d:{k:ids.get(v,v) if isinstance(v,str) else v for k,v in d.items()})
        self.registration['page_id']=self.page
        self.blocks={}
        for b in f.blocks:
            b['id']=ids[b['id']];b['parent']={'type':'page_id','page_id':self.page};self.blocks[b['id']]=b
        self.calls=[]
    def get(self,path):
        self.calls.append(path)
        if path.startswith('/pages/'):
            return {'object':'page','id':self.page},None
        value=copy.deepcopy(self.blocks[path.split('/')[-1]])
        value['request_id']=str(uuid.uuid4())
        return value,None
    def test_receive_repeat_and_unsubmitted_no_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'store'
            first=ingest(self.current,self.registration,root,get=self.get)
            second=ingest(self.current,self.registration,root,get=self.get)
            self.assertEqual(first['receipt']['id'],second['receipt']['id'])
            with self.assertRaises(ValueError):
                ingest(self.current,self.registration,root,get=lambda path:(None,{'reason':'network_unavailable'}))
            store=Receipts(root);self.assertEqual(store.db.execute('SELECT count(*) FROM receipts').fetchone()[0],1);store.close()
            self.blocks[self.registration['submit_block']]['to_do']['checked']=False
            self.calls=[];fresh=Path(tmp)/'no-submit'
            self.assertEqual(ingest(self.current,self.registration,fresh,get=self.get)['state'],'no_change')
            self.assertEqual(len(self.calls),2);self.assertFalse(fresh.exists())
    def test_moved_block_or_capture_change_never_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ident=self.registration['items']['01']['comment_block']
            self.blocks[ident]['parent']['page_id']=str(uuid.uuid4())
            with self.assertRaises(ValueError):ingest(self.current,self.registration,Path(tmp)/'moved',get=self.get)
            self.blocks[ident]['parent']['page_id']=self.page
            seen=0
            def unstable(path):
                nonlocal seen
                data,error=self.get(path)
                if path.endswith(ident):
                    seen+=1
                    if seen==2:data['paragraph']['rich_text']=[{'plain_text':'changed during capture'}]
                return data,error
            with self.assertRaisesRegex(ValueError,'during capture'):
                ingest(self.current,self.registration,Path(tmp)/'unstable',get=unstable)
            self.assertEqual(list(Path(tmp).iterdir()),[])


if __name__=='__main__':unittest.main()
