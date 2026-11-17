import io,json,os,sys,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from google_backtranslation import translate_json,backtranslate,preflight
from translation_review import create_item

class GoogleBacktranslationTests(unittest.TestCase):
    def test_blind_request_usage_and_decoding(self):
        seen=[]
        def open_request(req,timeout):
            seen.append(json.loads(req.data));self.assertEqual(timeout,30)
            return io.BytesIO(json.dumps({'data':{'translations':[{'translatedText':'慈悲 &amp; 智慧','detectedSourceLanguage':'id'}]}}).encode())
        with patch.dict(os.environ,{'GOOGLE_TRANSLATE_API_KEY':'TEST-NOT-A-REAL-KEY'}):
            result=translate_json(json.dumps({'q':'welas asih'}),'nmt',opener=open_request)
        self.assertEqual(seen,[{'q':'welas asih','target':'zh-CN','format':'text','model':'nmt'}])
        self.assertEqual(result['text'],'慈悲 & 智慧')
        self.assertEqual(result['usage']['input_characters'],10)
        self.assertIsNone(result['usage']['input_tokens'])

    def test_missing_key_stops_before_any_gemini_call(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'GOOGLE_TRANSLATE_API_KEY'):
                create_item({'original_exact':'text'},'id',{},provider=lambda *a:self.fail('unexpected model call'))

    def test_retries_only_explicit_rate_rejection_and_sanitizes_error(self):
        attempts=[];sleeps=[]
        def rejected(*args,**kwargs):
            attempts.append(1)
            raise urllib.error.HTTPError('https://secret.example/?key=SECRET',429,'SECRET',{},None)
        with patch.dict(os.environ,{'GOOGLE_TRANSLATE_API_KEY':'TEST'}):
            with self.assertRaisesRegex(RuntimeError,'^google_translate_http_429$'):
                translate_json('{"q":"x"}','nmt',opener=rejected,sleep=sleeps.append)
            self.assertEqual(len(attempts),3);self.assertEqual(sleeps,[1,2])
            attempts.clear()
            def unknown(*a,**kw):
                attempts.append(1);raise TimeoutError('SECRET')
            with self.assertRaisesRegex(RuntimeError,'^google_translate_outcome_unknown_check_before_retry$'):
                translate_json('{"q":"x"}','nmt',opener=unknown)
            self.assertEqual(len(attempts),1)

    def test_cache_and_unknown_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'GOOGLE_TRANSLATE_API_KEY':'TEST'}):
            with patch('google_backtranslation.translate_json',return_value={'text':'回译','provider':'google_translate'}) as api:
                a=backtranslate('target','id',workdir=d);b=backtranslate('target','id',workdir=d)
                self.assertEqual(a,b);self.assertEqual(api.call_count,1)
            with self.assertRaises(ValueError):backtranslate('changed','id',workdir=d)
            with patch('google_backtranslation.translate_json',side_effect=RuntimeError('unknown')) as api:
                with self.assertRaises(RuntimeError):backtranslate('t','id',workdir=Path(d)/'unknown')
                with self.assertRaises(RuntimeError):backtranslate('t','id',workdir=Path(d)/'unknown')
                self.assertEqual(api.call_count,1)

    def test_legacy_configuration_stops_before_gemini(self):
        for config in ({'backtranslation_provider':'gemini'}, {'backtranslation_model':'old-gemini-model'}):
            with self.subTest(config=config), patch.dict(os.environ,{'GOOGLE_TRANSLATE_API_KEY':'TEST-NOT-A-REAL-KEY'}):
                with self.assertRaises(ValueError):
                    create_item({'original_exact':'text'},'en',config,
                                provider=lambda *args:self.fail('must not call Gemini'))

if __name__=='__main__':unittest.main()
