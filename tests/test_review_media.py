import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from review_receiver import make_server
from review_html import render


class MediaTest(unittest.TestCase):
    def test_bound_http_ranges_hash_and_stale_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);video=root/'test.mp4';payload=b'byte-range-test-not-a-playable-video';video.write_bytes(payload)
            current={'schema_version':1,'task_id':'media-test','stage':'T4','language':'id','version':'v1',
                'batch':'test','round_id':'media-v1','entry':'local_html','items':[{'id':'01','version':'v1',
                'content':{'video':{'path':str(video),'sha256':hashlib.sha256(payload).hexdigest()}},
                'required_checks':['watch'],'approval_blockers':[]}]}
            rp=root/'round.json';page=root/'page.html'
            def save():
                rp.write_text(json.dumps(current));page.write_text(render(current))
            save();server=make_server(root/'store',rp,page);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                origin=f'http://127.0.0.1:{server.server_port}'
                with urllib.request.urlopen(origin+'/review',timeout=3) as r:html=r.read().decode()
                url=origin+re.search(r'src="(/media/[^"]+)"',html)[1]
                for range_header,expected in [('bytes=2-8',payload[2:9]),('bytes=-5',payload[-5:]),('bytes=10-',payload[10:])]:
                    with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':range_header}),timeout=3) as r:
                        self.assertEqual(r.status,206);self.assertEqual(r.read(),expected)
                with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=3) as r:
                    self.assertEqual(int(r.headers['Content-Length']),len(payload));self.assertEqual(r.read(),b'')
                def rejected(target,code,headers=None):
                    with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(urllib.request.Request(target,headers=headers or {}),timeout=3)
                    self.assertEqual(ctx.exception.code,code)
                rejected(url,416,{'Range':'bytes=999-'});rejected(origin+'/media/../../test.mp4',403)
                rejected(url,403,{'Host':'untrusted.example'})
                video.write_bytes(b'changed');rejected(url,409);video.write_bytes(payload)
                current['version']='v2';save();rejected(url,410)
                self.assertFalse((root/'store/review-signals').exists())
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)


if __name__=='__main__':unittest.main()
