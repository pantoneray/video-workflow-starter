import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from translation_review import temporary_gemini_backtranslation, make_version, model_stage

class BacktranslationChoiceTests(unittest.TestCase):
    def test_missing_config_guides_without_reading_source_or_touching_results(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=root/'models.json';cfg.write_text('{"backtranslation_model":"legacy-gemini"}')
            out=root/'existing.json';out.write_text('original result')
            env=dict(os.environ);env.pop('GOOGLE_TRANSLATE_API_KEY',None)
            script=Path(__file__).resolve().parents[1]/'scripts/translation_review.py'
            base=[sys.executable,str(script),'create','--source',str(root/'absent.json'),'--language','id','--models',str(cfg),'--out',str(out),'--confirm-external']
            r=subprocess.run(base,env=env,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(r.stdout)['state'],'needs_backtranslation_choice')
            self.assertEqual(out.read_text(),'original result')
            self.assertFalse(Path(str(out)+'.stages').exists())
            r=subprocess.run(base+['--temporary-gemini-backtranslation'],env=env,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(Path(str(out)+'.stages').exists())

    def test_temporary_blind_provider_is_labelled_and_cached(self):
        with tempfile.TemporaryDirectory() as d:
            prompts=[]
            def api(prompt,model):
                prompts.append(prompt)
                return {'items':[{'id':'1','translation':'回译'}]}
            stage=lambda st,pr,mo:model_stage(st,pr,mo,d,provider=api)
            evidence=temporary_gemini_backtranslation('target only','id','gemini-test','用户：本次用Gemini回译',stage)
            again=temporary_gemini_backtranslation('target only','id','gemini-test','用户：本次用Gemini回译',stage)
            self.assertEqual(evidence,again);self.assertEqual(len(prompts),1)
            self.assertEqual(evidence['provider'],'gemini')
            self.assertNotIn('PRIVATE_SOURCE',prompts[0])
            def review(stage,prompt,model):
                return {'items':[{'id':'1','review':'check','translation':'independent'}]}
            result=make_version({'original_exact':'PRIVATE_SOURCE'},'id','target only',{'review_model':'review','glossary':['PRIVATE_GLOSSARY']},stage_call=review,backtranslation_call=lambda *a:evidence)
            self.assertEqual(result['models']['backtranslation'],'gemini:gemini-test')
            self.assertEqual(result['human_decision'],'pending')
            self.assertIn('user_consent',result['backtranslation_evidence'])
            self.assertNotIn('PRIVATE_GLOSSARY',prompts[0])
            bad=dict(evidence);bad.pop('user_consent')
            with self.assertRaises(ValueError):make_version({'original_exact':'source'},'id','target',{'review_model':'review'},stage_call=review,backtranslation_call=lambda *a:bad)
            with self.assertRaises(ValueError):temporary_gemini_backtranslation('t','id','m',' ',stage)

    def test_unknown_temporary_request_does_not_resend(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def api(*a):calls.append(1);raise RuntimeError('unknown')
            stage=lambda st,pr,mo:model_stage(st,pr,mo,d,provider=api)
            for _ in range(2):
                with self.assertRaises(RuntimeError):temporary_gemini_backtranslation('t','id','m','本次同意',stage)
            self.assertEqual(len(calls),1)
