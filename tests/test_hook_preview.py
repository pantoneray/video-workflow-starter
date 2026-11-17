import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from hook_preview import plan, render_preview
from caption_templates import digest


class PreviewTest(unittest.TestCase):
    def test_complete_sentence_render_and_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);video=root/'synthetic.mp4';words=root/'words.json';text=root/'text.txt';receipt=root/'receipt.json'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=180x320:r=30:d=3',
                '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-c:a','aac',str(video)],check=True,timeout=30)
            text.write_text('First sentence. Second sentence.')
            words.write_text(json.dumps({'segments':[{'words':[{'word':'First sentence.','start':.1,'end':1.0},
                {'word':'Second sentence.','start':1.5,'end':2.5}]}]}))
            receipt.write_text(json.dumps({'output_sha256':digest(video),'words_sha256':digest(words),
                'approved_text_sha256':digest(text),'preserve_text':True,'decode':'PASS','template':'synthetic_fixture'}))
            p=plan(video,words,text,receipt,1,body_hook_mode='none')
            self.assertEqual(p['hook_text'],' Second sentence.')
            self.assertAlmostEqual(p['total_seconds_expected'],3+1.16+.2,places=2)
            result=render_preview(p,root/'draft')
            self.assertEqual(result['decode'],'PASS');self.assertFalse(result['prior_final_approval_reusable'])
            self.assertTrue(result['input_unchanged']);self.assertGreater(len(result['warnings']),1)
            with self.assertRaises(FileExistsError):render_preview(p,root/'draft')
            with self.assertRaisesRegex(ValueError,'combined'):plan(video,words,text,receipt,1,body_hook_mode='copy_frontload')
            with self.assertRaises(ValueError):plan(video,words,text,receipt,8,body_hook_mode='none')
            # Existing final trim is a different file; bind its unchanged manifest and source chain.
            final=root/'trimmed.mp4';srt=root/'actual.srt';manifest=root/'manifest.json';final_receipt=root/'final-receipt.json'
            subprocess.run(['ffmpeg','-v','error','-i',str(video),'-t','2.8','-c:v','libx264','-c:a','aac',str(final)],check=True,timeout=30)
            srt.write_text('1\n00:00:00,100 --> 00:00:01,000\nFirst sentence.\n\n2\n00:00:01,500 --> 00:00:02,500\nSecond sentence.\n')
            data=json.loads(receipt.read_text());data.update(output=str(video),source_sha256=digest(video));receipt.write_text(json.dumps(data))
            job={'video':str(video),'video_sha256':digest(video),'approved_text':str(text),'srt':str(srt),'end_s':2.8,'out':str(root)}
            manifest.write_text(json.dumps(job))
            fr={'manifest_sha256':digest(manifest),'sha256':digest(final),'output':str(final),'template':'synthetic_fixture'}
            final_receipt.write_text(json.dumps(fr))
            kwargs={'body_hook_mode':'none','finalization_receipt':final_receipt,'finalization_manifest':manifest}
            trimmed=plan(final,words,text,receipt,1,**kwargs)
            self.assertLess(trimmed['body_seconds'],p['body_seconds'])
            self.assertFalse(trimmed['finalization']['approval_inherited'])
            with self.assertRaisesRegex(ValueError,'output_sha256'):plan(final,words,text,receipt,1,body_hook_mode='none')
            srt.write_text(srt.read_text().replace('Second sentence.','Different sentence.'))
            with self.assertRaisesRegex(ValueError,'SRT'):plan(final,words,text,receipt,1,**kwargs)
            job['audio']='replacement.wav';manifest.write_text(json.dumps(job));fr['manifest_sha256']=digest(manifest);final_receipt.write_text(json.dumps(fr))
            with self.assertRaisesRegex(ValueError,'replacement audio'):plan(final,words,text,receipt,1,**kwargs)
            words.write_text(json.dumps({'segments':[{'words':[{'word':text.read_text(),'start':.1,'end':2.5}]}]}))
            data=json.loads(receipt.read_text());data['words_sha256']=digest(words);receipt.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'alignment unit'):plan(video,words,text,receipt,1,body_hook_mode='none')
            text.write_text('changed')
            with self.assertRaisesRegex(ValueError,'receipt'):plan(video,words,text,receipt,0,body_hook_mode='none')


if __name__=='__main__':unittest.main()
