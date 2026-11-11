#!/usr/bin/env python3
"""Read bounded user-owned term tables and select terms present in one source excerpt."""
import csv
import hashlib
import json
from pathlib import Path

from config_paths import resolve_path

FORMATS = {".csv", ".json", ".md", ".txt"}
MAX_FILES = 50
MAX_BYTES = 5_000_000
MAX_ROWS = 5000
MAX_MATCHES = 100


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not {"source", "target"} <= set(reader.fieldnames):
                raise ValueError("CSV 术语表需要 source,target 表头：" + path.name)
            yield from reader
        return
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items = data.get("terms") if isinstance(data, dict) else data
        if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
            raise ValueError("JSON 术语表须为对象数组或 {terms:[...]}：" + path.name)
        yield from items
        return
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#") or set(line) <= {"|", "-", ":", " "}:
            continue
        if "|" in line:
            cells = [part.strip() for part in line.strip("|").split("|")]
            if len(cells) not in (2, 3):
                raise ValueError(f"术语表第 {number} 行需为 source | target | 可选语言")
            source, target = cells[:2]
            language = cells[2] if len(cells) == 3 else ""
        elif "=" in line:
            source, target = (part.strip() for part in line.split("=", 1))
            language = ""
        else:
            raise ValueError(f"术语表第 {number} 行不是可解析的术语对")
        if source.casefold() in ("source", "中文", "原文") and target.casefold() in ("target", "译文", "目标语"):
            continue
        yield {"source": source, "target": target, "language": language}


def select(config, original, target_language, base_dir=None):
    paths = (config.get("paths") or {}).get("glossary") or []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        raise ValueError("项目 glossary 路径须为文件或列表")
    selected = {}
    file_count = row_count = 0
    for entry in paths:
        root = resolve_path(entry, base_dir)
        if not root.exists():
            raise FileNotFoundError("术语表路径不可用：" + str(root))
        files = ([root] if root.is_file() else
                 sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                        and not p.name.startswith(".")))
        for path in files:
            file_count += 1
            if file_count > MAX_FILES:
                raise ValueError("术语表超过文件数上限；请缩小配置范围")
            if path.suffix.lower() not in FORMATS:
                raise ValueError("术语表含不支持格式：" + path.name)
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("术语表文件过大：" + path.name)
            file_sha = digest(path)
            for item in rows(path):
                row_count += 1
                if row_count > MAX_ROWS:
                    raise ValueError("术语表条目过多；请缩小配置范围")
                source, target = str(item.get("source") or "").strip(), str(item.get("target") or "").strip()
                language = str(item.get("language") or "").strip()
                if not source or not target:
                    raise ValueError("术语表 source/target 不能为空：" + path.name)
                if language and language.casefold() != target_language.casefold():
                    continue
                if source.casefold() not in original.casefold():
                    continue
                key = source.casefold()
                if key in selected and selected[key]["target"] != target:
                    raise ValueError("同一原文术语有冲突译法：" + source)
                selected[key] = {"source": source, "target": target, "language": language or target_language,
                                 "source_file": str(path), "source_sha256": file_sha,
                                 "note": str(item.get("note") or "")[:500],
                                 "status": "provided_for_human_review"}
                if len(selected) > MAX_MATCHES:
                    raise ValueError("当前摘录命中术语过多；请缩小术语表或原文范围")
    return list(selected.values())
