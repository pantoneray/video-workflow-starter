"""Read an existing paragraph_fts index without building or modifying it.

This adapter verifies indexed rows, not the original EPUB bytes. All paths are
user configuration; no workstation-specific corpus path belongs in the package.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager

FIELDS = ('id', 'book_id', 'book_title', 'chapter', 'paragraph_index',
          'source_epub', 'source_xhtml', 'text')


@contextmanager
def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    deadline = time.monotonic() + 10
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        yield db
    finally:
        db.close()


def evidence(db, row):
    item = {key: row[key] for key in FIELDS}
    for side, comparator, ordering in (('before', '<', 'DESC'), ('after', '>', 'ASC')):
        neighbor = db.execute(
            f'SELECT id, paragraph_index, text FROM paragraphs WHERE book_id=? AND chapter=? '
            f'AND paragraph_index {comparator} ? ORDER BY paragraph_index {ordering}, id LIMIT 1',
            (row['book_id'], row['chapter'], row['paragraph_index'])).fetchone()
        item['context_' + side] = dict(neighbor) if neighbor else None
    return item


def digest(item):
    return hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def source_record(path, item):
    return {'kind': 'sqlite_paragraph', 'file': str(Path(path).resolve()),
            'row_id': item['id'], 'sha256': digest(item),
            'hash_scope': 'indexed_row_and_same_chapter_neighbors_not_epub',
            'locator': f"{item['book_title']} | {item['chapter']} | paragraph {item['paragraph_index']}",
            'source_epub': item['source_epub'], 'source_xhtml': item['source_xhtml'],
            'original_exact': item['text'],
            'context_before': (item['context_before'] or {}).get('text', ''),
            'context_after': (item['context_after'] or {}).get('text', ''),
            'context_note': '同章节相邻索引段落；原始 EPUB 尚未逐字核验，不代表语义审核通过'}


def verify_index_source(source):
    with connect(source['file']) as db:
        db.execute('BEGIN')
        row = db.execute('SELECT * FROM paragraphs WHERE id=?', (source['row_id'],)).fetchone()
        if row is None:
            raise ValueError('indexed source row missing')
        current = source_record(source['file'], evidence(db, row))
    if any(source.get(key) != value for key, value in current.items()):
        raise ValueError('indexed source or context changed')


def search_index(path, theme, max_results=30):
    if not theme.get('enabled', False) or not 1 <= max_results <= 1000:
        raise ValueError('enabled theme and result limit 1..1000 required')
    words = [str(x).strip() for x in theme.get('keywords', []) if str(x).strip()]
    if not words or len(words) > 50:
        raise ValueError('index search requires 1..50 keywords')
    query = ' OR '.join('"' + word.replace('"', '""') + '"' for word in words)
    results = []
    with connect(path) as db:
        db.execute('BEGIN')
        # Schema incompatibility raises explicitly. No implicit rebuild or write.
        rows = db.execute('SELECT p.*, rank FROM paragraph_fts f JOIN paragraphs p ON p.id=f.rowid '
                          'WHERE paragraph_fts MATCH ? ORDER BY rank LIMIT ?',
                          (query, max_results * 5)).fetchall()
        for row in rows:
            text = row['text']
            if any(str(w).casefold() in text.casefold() for w in theme.get('exclude_keywords', [])):
                continue
            source = source_record(path, evidence(db, row))
            results.append({**source, 'source': source, 'retrieval': 'sqlite_fts5',
                            'theme_id': theme['id'], 'rank': row['rank'],
                            'approval': 'pending_human_review'})
            if len(results) == max_results:
                break
    return {'results': results, 'retrieval': 'sqlite_fts5',
            'coverage': 'FTS5词元命中正文或书名/章节；有候选上限，不是全文子串或语义RAG；只验证索引记录'}
