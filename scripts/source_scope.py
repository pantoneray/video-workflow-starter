"""Source choice using a configured existing FTS index or readable text files.

No second index or claimed semantic RAG. Missing sources are reported.
"""
import argparse
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from config_paths import resolve_path
from source_search import ALLOWED, search
from source_index import search_index


def search_sources(config, themes, theme_id, source_type="auto", base_dir=None, max_results=30):
    if source_type not in ("auto", "corpus", "srt"):
        raise ValueError("source_type must be auto, corpus or srt")
    theme = next(x for x in themes["themes"] if x.get("id") == theme_id)
    if not theme.get('enabled', False) or not theme.get('keywords') or not 1 <= max_results <= 1000:
        raise ValueError('enabled theme, keywords and result limit 1..1000 required')
    scope = theme.get("source_scope") or ["life_corpus", "deep_corpus", "subtitle_sources"]
    if "subtitle_sources" in config.get("paths", {}) and "subtitle_sources" not in scope:
        scope = [*scope, "subtitle_sources"]
    result = {"source_type": source_type, "retrieval": "existing_keyword_search", "results": [], "warnings": [],
              "searched_types": [], "missing_types": [], "duplicates": [], "files_scanned": 0}
    files = {"corpus": [], "srt": []}
    index = config.get('source_index', {})
    indexed = None
    if source_type != 'srt' and index:
        try:
            if index.get('type') != 'paragraph_fts' or not index.get('path'):
                raise ValueError('unsupported source_index configuration')
            indexed = search_index(resolve_path(index['path'], base_dir), theme, max_results)
            result['retrieval'] = 'sqlite_fts5_and_available_srt_keyword_search'
            result['index_coverage'] = indexed['coverage']
        except (OSError, ValueError, sqlite3.Error) as exc:
            result['warnings'].append({'group': 'corpus', 'reason': 'index_unavailable', 'error_type': type(exc).__name__})
            # A configured index defines the corpus scope; do not silently substitute other sources.
            indexed = {'results': [], 'failed': True}
    visited = set()
    for group in scope:
        roots = config.get("paths", {}).get(group, [])
        if isinstance(roots, str):
            roots = [roots]
        if not roots:
            result["warnings"].append({"group": group, "reason": "not_configured"})
        for root in roots:
            path = resolve_path(root, base_dir)
            if not path.exists():
                result["warnings"].append({"group": group, "reason": "path_unavailable", "path": str(path)})
                continue
            for file in ([path] if path.is_file() else sorted(path.rglob("*"))):
                if file.is_file() and file.suffix.lower() in ALLOWED and str(file.resolve()) not in visited:
                    visited.add(str(file.resolve()))
                    kind = "srt" if file.suffix.lower() == ".srt" else "corpus"
                    if kind == 'corpus' and indexed is not None:
                        continue
                    files[kind].append(str(file.resolve()))
    seen = {}
    for kind in (("corpus", "srt") if source_type == "auto" else (source_type,)):
        if kind == 'corpus' and indexed is not None:
            result['missing_types' if indexed.get('failed') else 'searched_types'].append(kind)
            for item in indexed['results']:
                fingerprint = hashlib.sha256(item['original_exact'].encode()).hexdigest()
                if fingerprint in seen:
                    result['duplicates'].append({'file': item['file'], 'locator': item['locator'], 'same_text_as': seen[fingerprint]})
                    continue
                seen[fingerprint] = {'file': item['file'], 'locator': item['locator']}
                result['results'].append(item)
            continue
        if not files[kind]:
            result["missing_types"].append(kind)
            continue
        # Each source separately: one unreadable source must not erase other evidence.
        successful = False
        for filename in files[kind]:
            isolated_theme = {**theme, "source_scope": [kind]}
            try:
                found = search({"paths": {kind: [filename]}}, {"themes": [isolated_theme]}, theme_id,
                               max_results=max_results)
            except (OSError, ValueError, RuntimeError) as exc:
                result["warnings"].append({"file": filename, "reason": type(exc).__name__})
                continue
            successful = successful or found["files_scanned"] > 0
            result["files_scanned"] += found["files_scanned"]
            result["warnings"].extend(found["warnings"])
            for item in found["results"]:
                fingerprint = hashlib.sha256(item["original_exact"].encode()).hexdigest()
                if fingerprint in seen:
                    result["duplicates"].append({"file": item["file"], "locator": item["locator"], "same_text_as": seen[fingerprint]})
                    continue
                seen[fingerprint] = {"file": item["file"], "locator": item["locator"]}
                if len(result["results"]) < max_results:
                    result["results"].append(item)
        if successful:
            result["searched_types"].append(kind)
        else:
            result["missing_types"].append(kind)
    result["coverage"] = "仅实际可读文件或明确配置的索引关键词检索；候选受数量上限限制，不代表语义或全库审核"
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True); p.add_argument("--themes", required=True)
    p.add_argument("--theme-id", required=True); p.add_argument("--source-type", choices=("auto", "corpus", "srt"), default="auto")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    config = Path(a.config).resolve()
    result = search_sources(json.loads(config.read_text()), json.loads(Path(a.themes).read_text()), a.theme_id,
                            a.source_type, config.parent)
    with Path(a.out).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
