"""Managed Git text libraries; user data stays outside the installed Skill."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from config_paths import resolve_path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'config' / 'libraries.example.json'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def git(path, *args, network=False):
    command = ['git', '-c', 'core.hooksPath=', '-C', str(path), *args]
    attempts = 3 if network else 1
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
    for attempt in range(attempts):
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=180 if network else 30, env=env)
            if result.returncode == 0:
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    # Do not expose remote URLs, credentials or raw transport errors.
    raise RuntimeError('git_request_failed' if network else 'git_local_check_failed')


def outside_skill(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('资料和个人配置须放在 Skill 安装目录外')
    return path


@contextmanager
def locked(config_path, ident):
    if not ident or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in ident):
        raise ValueError('invalid_library_id')
    parent = Path(config_path).resolve().parent / '.video-workflow-locks'
    parent.mkdir(exist_ok=True)
    lock = parent / (ident + '.lock')
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('library_busy；已有操作未结束，异常退出后先核查再删除锁目录') from None
    try:
        yield
    finally:
        lock.rmdir()


def entry(config_path, ident):
    config = read_json(config_path)
    info = config.get('libraries', {}).get(ident)
    if not info or not info.get('enabled', True):
        raise ValueError('library_not_configured')
    return info, resolve_path(info['path'], Path(config_path).resolve().parent)


def repo_state(path, repository):
    if not shutil.which('git'):
        raise ValueError('missing_git；请让 Codex 安装 Git 后重试')
    if Path(git(path, 'rev-parse', '--show-toplevel')).resolve() != Path(path).resolve():
        raise ValueError('not_library_repository_root')
    if git(path, 'remote', 'get-url', 'origin').rstrip('/') != repository.rstrip('/'):
        raise ValueError('repository_origin_mismatch；保留现有目录，不自动改源')
    dirty = bool(git(path, 'status', '--porcelain', '--untracked-files=normal'))
    return {'commit': git(path, 'rev-parse', 'HEAD'), 'dirty': dirty}


def save_config(path, config):
    path = Path(path).resolve()
    # Exact pre-change copy; no account files or unrelated config keys are replaced.
    backup = path.with_name(path.name + '.before-library-' + uuid.uuid4().hex[:10] + '.bak')
    shutil.copy2(path, backup)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        shutil.copymode(path, temp)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return str(backup)


def setup(config_path, ident='suodj', destination=None, definition=None):
    config_path = outside_skill(config_path)
    config = read_json(config_path)
    definition = definition or read_json(CATALOG)[ident]
    current = config.get('libraries', {}).get(ident)
    if current:
        if destination and resolve_path(destination) != resolve_path(current['path'], config_path.parent):
            raise ValueError('已有登记路径；不自动移动知识库')
        path = outside_skill(resolve_path(current['path'], config_path.parent))
        state = repo_state(path, current['repository'])
        return {'state': 'already_installed', 'library': ident, 'path': str(path), **state}
    path = outside_skill(resolve_path(destination, config_path.parent) if destination else
                         config_path.parent / '资料库' / ident)
    if path == config_path.parent or path in config_path.parents:
        raise ValueError('library_path_cannot_contain_project_config')
    with locked(config_path, ident):
        if path.exists():
            # Reuse an explicit existing Smart Library clone; never take over arbitrary folders.
            state = repo_state(path, definition['repository'])
            if state['dirty']:
                raise ValueError('library_has_local_changes；保留修改后再接入')
        else:
            if not shutil.which('git'):
                raise ValueError('missing_git；请让 Codex 安装 Git 后重试')
            path.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='.' + ident + '-download-', dir=path.parent))
            try:
                git(path.parent, 'clone', '--depth', '1', '--', definition['repository'], str(staging), network=True)
                state = repo_state(staging, definition['repository'])
                staging.rename(path)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        try:
            saved_path = os.path.relpath(path, config_path.parent)
        except ValueError:  # Windows project and reused library can be on different drives.
            saved_path = str(path)
        config.setdefault('libraries', {})[ident] = {
            'enabled': True, 'repository': definition['repository'],
            'path': saved_path,
            'source_groups': definition.get('source_groups', ['life_corpus', 'deep_corpus']),
            'directories': definition.get('directories', [])}
        backup = save_config(config_path, config)
    return {'state': 'installed', 'library': ident, 'path': str(path), **state, 'config_backup': backup}


def status(config_path, ident='suodj'):
    info, path = entry(config_path, ident)
    with locked(config_path, ident):
        return {'state': 'local_available', 'library': ident, 'path': str(path),
                **repo_state(path, info['repository']), 'remote_checked': False}


def update(config_path, ident='suodj'):
    info, path = entry(config_path, ident)
    with locked(config_path, ident):
        before = repo_state(path, info['repository'])
        if before['dirty']:
            raise ValueError('library_has_local_changes；不覆盖、不 reset，请先处理个人修改')
        # Fetch can be retried, merge is local and fast-forward only. Never force reset.
        try:
            git(path, 'fetch', 'origin', network=True)
        except RuntimeError:
            return {'state': 'update_unavailable', 'library': ident, **before,
                    'local_available': True, 'requires_user_choice': '是否用已下载版本继续',
                    'error': 'network_or_remote_unavailable'}
        git(path, 'merge', '--ff-only', '@{upstream}')
        after = repo_state(path, info['repository'])
    return {'state': 'updated' if before['commit'] != after['commit'] else 'up_to_date',
            'library': ident, 'before': before['commit'], **after}


def ordered_documents(root, directories):
    """Metadata list order within each folder; omit hidden dirs, resources and symlinks."""
    def walk(folder):
        meta_path = folder / '.meta.json'
        metadata = read_json(meta_path) if meta_path.is_file() and not meta_path.is_symlink() and meta_path.stat().st_size < 2_000_000 else {}
        order = {x['name']: n for n, x in enumerate(metadata.get('list', []))
                 if isinstance(x, dict) and isinstance(x.get('name'), str)}
        children = sorted(folder.iterdir(), key=lambda x: (order.get(x.name, len(order)), x.name))
        docs = [x for x in children if x.is_file() and not x.is_symlink() and x.suffix.lower() in ('.md', '.markdown', '.txt') and not x.name.startswith('.')]
        for n, file in enumerate(docs):
            yield file, meta_path if meta_path.is_file() and not meta_path.is_symlink() else None, metadata, {
                'previous': str(docs[n-1].relative_to(root)) if n else None,
                'next': str(docs[n+1].relative_to(root)) if n+1 < len(docs) else None}
        for child in children:
            if child.is_dir() and not child.is_symlink() and not child.name.startswith('.'):
                yield from walk(child)
    for directory in directories:
        folder = resolve_path(directory, root)
        if folder == root or root not in folder.parents:
            raise ValueError('library_directories_must_be_relative_subfolders')
        if folder.is_dir():
            yield from walk(folder)


def search_libraries(config, theme, max_results, base_dir):
    from source_search import search_files
    scope = theme.get('source_scope') or ['life_corpus', 'deep_corpus']
    selected = [(ident, info) for ident, info in config.get('libraries', {}).items()
                if info.get('enabled', True) and set(info.get('source_groups', [])) & set(scope)
                and ('library_ids' not in theme or ident in theme['library_ids'])]
    report = {'results': [], 'warnings': [], 'files_scanned': 0, 'libraries': [],
              'coverage': '按主题关键词检索；达到候选上限后停止，不代表语义匹配或全库已审'}
    if not selected:
        return report
    if base_dir is None:
        raise ValueError('library_search_needs_config_directory')
    seen = set()
    for ident, info in selected:
        if len(report['results']) >= max_results:
            break
        root = resolve_path(info['path'], base_dir)
        with locked(Path(base_dir) / 'video-config.json', ident):
            state = repo_state(root, info['repository'])
            if state['dirty']:
                raise ValueError('library_has_local_changes；请核查或使用已保存任务快照')
            report['libraries'].append({'id': ident, 'repository': info['repository'], **state})
            for file, meta_path, metadata, neighbors in ordered_documents(root, info.get('directories', [])):
                found = search_files({'paths': {'library': [str(file)]}}, {'themes': [
                    {**theme, 'source_scope': ['library']}]}, theme['id'], max_files=1,
                    max_results=max_results-len(report['results']))
                report['files_scanned'] += found['files_scanned']
                report['warnings'].extend(found['warnings'])
                if not found['results']:
                    continue
                raw = file.read_bytes()
                text = raw.decode('utf-8-sig')
                digest = hashlib.sha256(raw).hexdigest()
                for item in found['results']:
                    # Images are not narration. Keep exact source text, require explicit review for markup.
                    if item['original_exact'].lstrip().startswith('!['):
                        continue
                    fingerprint = hashlib.sha256(''.join(item['original_exact'].split()).encode()).hexdigest()
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    if item['source_sha256'] != digest:
                        raise ValueError('library_changed_during_search')
                    start = text.find(item['original_exact'])
                    if start < 0:
                        raise ValueError('library_excerpt_not_exact')
                    source = {'file': str(file), 'sha256': digest, 'start': start,
                              'end': start+len(item['original_exact']), 'original_exact': item['original_exact'],
                              'locator': str(file.relative_to(root)) + ' | ' + item['locator'],
                              'context_before': item['context_before'], 'context_after': item['context_after'],
                              'library_id': ident, 'repository': info['repository'], 'commit': state['commit'],
                              'relative_path': str(file.relative_to(root)), 'neighbor_documents': neighbors}
                    item.update(source=source, library_id=ident, repository=info['repository'], commit=state['commit'],
                                relative_path=source['relative_path'], book=file.parent.name,
                                metadata=metadata.get('*', {}), neighbor_documents=neighbors)
                    if meta_path:
                        source['metadata_file'] = str(meta_path)
                        source['metadata_sha256'] = hashlib.sha256(meta_path.read_bytes()).hexdigest()
                    if '![' in item['original_exact']:
                        item['review_flags'].append('含图片标记；口播选文须排除标记后重新核对逐字范围')
                    report['results'].append(item)
                if len(report['results']) >= max_results:
                    break
            after = repo_state(root, info['repository'])
            if after != state:
                raise ValueError('library_changed_during_search；重试检索，不沿用混合版本')
    return report


def freeze_report(report, out):
    """Only used source files and metadata, never a second copy of the entire library."""
    sources = [item for item in report.get('results', []) if item.get('library_id')]
    if not sources:
        return report
    directory = Path(str(out) + '.sources')
    directory.mkdir(exist_ok=False)
    try:
        for item in sources:
            source = dict(item['source'])
            source['live_file'] = source['file']
            for path_key, hash_key in [('file', 'sha256'), ('metadata_file', 'metadata_sha256')]:
                if path_key not in source:
                    continue
                original = Path(source[path_key]);data = original.read_bytes()
                if hashlib.sha256(data).hexdigest() != source[hash_key]:
                    raise ValueError('library_changed_before_snapshot')
                target = directory / (source[hash_key] + original.suffix)
                if not target.exists():
                    target.write_bytes(data)
                source[path_key] = str(target.resolve())
            item['source'] = source
            item['file'] = source['file']
            item['snapshot'] = True
        return report
    except Exception:
        shutil.rmtree(directory)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'update', 'status'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--library', default='suodj')
    parser.add_argument('--path', help='setup时可指定已同步目录或下载位置，默认项目/资料库/suodj')
    args = parser.parse_args()
    try:
        if args.command == 'setup':
            result = setup(args.config, args.library, args.path)
        elif args.command == 'update':
            result = update(args.config, args.library)
        else:
            result = status(args.config, args.library)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({'state': 'action_required', 'reason': str(exc),
                          'existing_files_preserved': True}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
