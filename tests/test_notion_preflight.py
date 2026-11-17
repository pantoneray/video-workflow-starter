import io,json,sys,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from notion_preflight import check


class NotionPreflightTest(unittest.TestCase):
    def test_missing_no_network_and_read_only_success(self):
        opener=Mock();page='00000000-0000-0000-0000-000000000001'
        self.assertEqual(check(page,token='',opener=opener)['state'],'not_configured');opener.assert_not_called()
        opener.side_effect=[io.BytesIO(json.dumps(x).encode()) for x in [
            {'type':'bot','id':'test','bot':{'workspace_name':'test'}},
            {'object':'page','url':'https://notion.so/test'}, {'object':'list','results':[]}]]
        result=check(page,token='secret',opener=opener)
        self.assertEqual(result['state'],'read_access_verified');self.assertEqual(result['write_permission'],'not_tested')
        self.assertNotIn('secret',json.dumps(result))
        for args,kwargs in opener.call_args_list:
            self.assertEqual(args[0].get_method(),'GET');self.assertEqual(kwargs['timeout'],20)

    def test_permission_does_not_retry_or_leak_error(self):
        page='00000000-0000-0000-0000-000000000001'
        opener=Mock(side_effect=urllib.error.HTTPError('secret-url',401,'secret',{},io.BytesIO(b'')));sleep=Mock()
        result=check(page,token='secret',opener=opener,sleep=sleep)
        self.assertEqual(result['http_status'],401);self.assertNotIn('secret',json.dumps(result));sleep.assert_not_called()
        opener=Mock(side_effect=urllib.error.HTTPError('secret-url',429,'secret',{},io.BytesIO(b'')))
        check(page,token='secret',opener=opener,sleep=sleep)
        self.assertEqual(opener.call_count,3);self.assertEqual([x.args[0] for x in sleep.call_args_list],[1,2])


if __name__=='__main__':unittest.main()
