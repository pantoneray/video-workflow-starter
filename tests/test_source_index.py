import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from source_scope import search_sources
from source_index import connect
from review_html import verify_source, render
from hook_copy import copy_proposal, review_round


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'corpus.sqlite'
        with sqlite3.connect(self.path) as db:
            db.executescript('''CREATE TABLE paragraphs(id INTEGER PRIMARY KEY, book_id TEXT,
                book_title TEXT, chapter TEXT, paragraph_index INTEGER, source_epub TEXT,
                source_xhtml TEXT, text TEXT);
                CREATE VIRTUAL TABLE paragraph_fts USING fts5(text, book_title, chapter,
                content='paragraphs', content_rowid='id');''')
            for n, text in enumerate(('前文。', '慈悲 是重要的。请保留完整语义。', '后文。')):
                db.execute('INSERT INTO paragraphs VALUES(?,?,?,?,?,?,?,?)',
                           (n+1, 'book', '原书', '本章', n, 'book.epub', 'chapter.xhtml', text))
            db.execute("INSERT INTO paragraph_fts(paragraph_fts) VALUES('rebuild')")
        self.config = {'source_index': {'type': 'paragraph_fts', 'path': str(self.path)}}
        self.themes = {'themes': [{'id': 'daily', 'enabled': True, 'keywords': ['慈悲']}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_real_sqlite_to_review_and_readonly(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        result = search_sources(self.config, self.themes, 'daily')
        source = result['results'][0]['source']
        self.assertEqual(source['context_before'], '前文。')
        self.assertEqual(source['context_after'], '后文。')
        self.assertEqual(result['searched_types'], ['corpus'])
        self.assertEqual(result['missing_types'], ['srt'])
        verify_source(source)
        proposal = copy_proposal(source, 0, characters_per_minute=240, rate_basis='test estimate')
        current = review_round(proposal, task_id='t', item_id='1', batch='b', version='v1', round_id='r1')
        self.assertIn('未逐字核验原始 EPUB', render(current))
        with connect(self.path) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM paragraphs')
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE paragraphs SET text='前文改变。' WHERE id=1")
        with self.assertRaisesRegex(ValueError, 'changed'):
            verify_source(source)

    def test_dedup_and_explicit_srt(self):
        srt = self.root / 'clip.srt'
        srt.write_text('1\n00:00:01,000 --> 00:00:05,000\n慈悲 是重要的。请保留完整语义。\n')
        self.config['paths'] = {'subtitle_sources': [str(srt)]}
        result = search_sources(self.config, self.themes, 'daily')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(len(result['duplicates']), 1)
        self.assertEqual(result['searched_types'], ['corpus', 'srt'])
        self.config['source_index']['path'] = str(self.root / 'nonexistent.sqlite')
        result = search_sources(self.config, self.themes, 'daily', 'srt')
        self.assertEqual(result['searched_types'], ['srt'])
        self.assertFalse(any(w.get('reason') == 'index_unavailable' for w in result['warnings']))

    def test_missing_index_no_silent_fallback_or_create(self):
        missing = self.root / 'missing.sqlite'
        self.config['source_index']['path'] = str(missing)
        raw = self.root / 'raw.txt'; raw.write_text('慈悲')
        self.config['paths'] = {'life_corpus': [str(raw)]}
        result = search_sources(self.config, self.themes, 'daily', 'corpus')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['missing_types'], ['corpus'])
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
