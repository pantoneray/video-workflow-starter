import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from knowledge_library import setup, update, status, locked, freeze_report
from source_search import search
from source_scope import search_sources
from review_html import verify_source
from project_setup import initialize
from guide import plan


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.remote = self.root / 'remote';self.remote.mkdir()
        self.run_git(self.remote, 'init', '-b', 'main')
        self.book = self.remote / '著作' / '原书';self.book.mkdir(parents=True)
        (self.book / 'a.md').write_text('# 第一章\n\n慈悲是倾听他人时保留完整语境和具体处境的行动。\n\n后文。\n')
        (self.book / 'z.md').write_text('# 第二章\n\n慈悲也需要关注每一个人的具体处境，不能简单地一概而论。\n')
        (self.book / '.meta.json').write_text(json.dumps({'*': {'kind': ['test']}, 'list': [{'name': 'z.md'}, {'name': 'a.md'}]}))
        self.commit('initial')
        self.project=self.root/'project';self.project.mkdir()
        self.config=self.project/'config.json'
        self.original={'paths':{'output': str(self.project)},'personal':{'keep':'yes'},'libraries':{}}
        self.config.write_text(json.dumps(self.original))
        self.definition={'repository':self.remote.as_uri(),'directories':['著作'],'source_groups':['life_corpus','deep_corpus']}
        self.themes={'themes':[{'id':'theme','enabled':True,'keywords':['慈悲'],'source_scope':['life_corpus']}]}

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, cwd, *args):
        return subprocess.run(['git','-C',str(cwd),*args],capture_output=True,text=True,check=True).stdout.strip()

    def commit(self, message):
        self.run_git(self.remote,'add','--all')
        self.run_git(self.remote,'-c','user.name=Test','-c','user.email=test@example.com','commit','-m',message)

    def install(self):
        setup(self.config,definition=self.definition)
        return self.project/'资料库/suodj'

    def test_setup_repeat_config_backup_and_project_memory(self):
        before=self.config.read_bytes();path=self.install()
        config=json.loads(self.config.read_text())
        self.assertEqual(config['personal'],self.original['personal'])
        self.assertEqual(config['paths'],self.original['paths'])
        backups=list(self.project.glob('*.bak'));self.assertEqual(backups[0].read_bytes(),before)
        saved=self.config.read_bytes()
        self.assertEqual(setup(self.config,definition=self.definition)['state'],'already_installed')
        self.assertEqual(self.config.read_bytes(),saved)
        self.assertEqual(status(self.config)['state'],'local_available')
        initialize(self.config,self.project)
        self.assertIn(str(path),(self.project/'VIDEO-WORKFLOW-MEMORY.md').read_text())
        report=plan(self.config,stage='source',environment_runner=lambda *a,**k:subprocess.CompletedProcess([],0,'PASS\n',''))
        self.assertEqual(report['stages'][0]['path_blockers'],[])

    def test_update_changes_additions_deletions_and_frozen_source(self):
        path=self.install();config=json.loads(self.config.read_text())
        found=search(config,self.themes,'theme',max_results=2,base_dir=self.project)
        self.assertEqual([x['relative_path'] for x in found['results']],['著作/原书/z.md','著作/原书/a.md'])
        self.assertEqual(found['results'][0]['source']['neighbor_documents']['next'],'著作/原书/a.md')
        found=freeze_report(found,self.project/'candidates.json')
        source=found['results'][0]['source'];verify_source(source)
        self.assertEqual(update(self.config)['state'],'up_to_date')
        (self.book/'z.md').unlink()
        (self.book/'a.md').write_text('# 第一章\n\n慈悲改动后的内容，应该只影响下一项新任务。\n')
        (self.book/'new.md').write_text('# 新章\n\n慈悲新增内容，必须保存真实出处。\n')
        self.commit('changed')
        updated=update(self.config);self.assertEqual(updated['state'],'updated')
        self.assertFalse((path/'著作/原书/z.md').exists())
        self.assertTrue((path/'著作/原书/new.md').exists())
        verify_source(source)  # deleted live source still reviewable from task snapshot
        next_found=search_sources(config,self.themes,'theme',base_dir=self.project)
        self.assertNotEqual(next_found['results'][0]['commit'],source['commit'])
        self.assertEqual(source['original_exact'],found['results'][0]['original_exact'])

    def test_dirty_lock_remote_failure_and_other_folder_preserve(self):
        path=self.install();file=path/'著作/原书/a.md';file.write_text('我的修改')
        with self.assertRaisesRegex(ValueError,'local_changes'):update(self.config)
        self.assertEqual(file.read_text(),'我的修改')
        with locked(self.config,'suodj'):
            with self.assertRaisesRegex(ValueError,'library_busy'):status(self.config)
        self.run_git(path,'restore','著作/原书/a.md')
        import knowledge_library
        actual=knowledge_library.git
        def failed(path,*args,**kw):
            if kw.get('network'):raise RuntimeError('network')
            return actual(path,*args,**kw)
        with patch('knowledge_library.git',side_effect=failed):
            r=update(self.config)
        self.assertEqual(r['state'],'update_unavailable');self.assertTrue(r['local_available'])
        self.assertTrue(search(json.loads(self.config.read_text()),self.themes,'theme',base_dir=self.project)['results'])
        self.run_git(path,'remote','set-url','origin',str(self.root/'wrong'))
        with self.assertRaisesRegex(ValueError,'origin_mismatch'):setup(self.config,definition=self.definition)
        self.assertTrue(file.exists())

    def test_more_than_500_files_and_cli_snapshot(self):
        for n in range(505):
            (self.book/f'doc{n:04}.md').write_text('这里没有要找的词。\n')
        (self.book/'zz-end.md').write_text('# 正文\n\n唯一末尾命中的完整内容，必须能跨过五百个文件的旧限制。\n')
        self.commit('large')
        self.install()
        themes={'themes':[dict(self.themes['themes'][0],keywords=['唯一末尾'])]}
        theme_path=self.project/'topics.json';theme_path.write_text(json.dumps(themes))
        script=Path(__file__).resolve().parents[1]/'workflow.py'
        out=self.project/'审核/candidates.json'
        args=[sys.executable,str(script),'source','--config',str(self.config),'--themes',str(theme_path),'--theme-id','theme','--out',str(out)]
        subprocess.run(args,check=True,capture_output=True)
        report=json.loads(out.read_text());self.assertGreater(report['files_scanned'],500)
        verify_source(report['results'][0]['source'])
        before=out.read_bytes()
        self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
        self.assertEqual(out.read_bytes(),before)
        only_srt=search_sources(json.loads(self.config.read_text()),themes,'theme','srt',base_dir=self.project)
        self.assertNotIn('corpus',only_srt['searched_types'])

    def test_existing_clone_can_be_registered_without_reclone(self):
        existing=self.root/'existing'
        self.run_git(self.root,'clone',self.definition['repository'],str(existing))
        before=self.run_git(existing,'rev-parse','HEAD')
        result=setup(self.config,destination=existing,definition=self.definition)
        self.assertEqual(result['commit'],before)
        self.assertEqual(json.loads(self.config.read_text())['libraries']['suodj']['path'],os.path.relpath(existing,self.project))
