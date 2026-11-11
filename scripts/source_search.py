#!/usr/bin/env python3
"""Bounded, exact-text topic search in user-specified corpora."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from config_paths import resolve_path

ALLOWED = {".md", ".markdown", ".txt", ".pdf"}
LEADING_REFERENCE = re.compile(r"^(?:这|那|此|其|他|她|它|上述|前者|后者|因此|所以|但是|然而|接着|这里|这种|那种)")
CONTEXT_DEPENDENT = re.compile(r"^(?:因此|所以|但是|然而|接着|例如|比如|第二|第三|其二|其三|如上所说|前面提到)")


def candidate_risks(original, before_item, after_item, section, hits, depth):
    """Mechanical review prompts only; no semantic approval or rejection."""
    risks = []

    def add(code, evidence, action):
        risks.append({"code": code, "status": "needs_human_review", "evidence": evidence, "action": action})

    if len(original) < 30:
        add("short_excerpt", f"{len(original)} 字符", "回到完整段落确认前提与指代")
    match = LEADING_REFERENCE.match(original)
    if match:
        add("leading_reference", match.group(), "核对代词或承接词指向，必要时扩大摘录范围")
    match = CONTEXT_DEPENDENT.match(original)
    if match and not before_item:
        add("missing_previous_context", match.group(), "缺上文；须回原文查清前提")
    if original.rstrip().endswith(("：", ":", "，", ",", "、")):
        add("unfinished_ending", original.rstrip()[-1], "末尾依赖后文；须连同后文核对")
    if section and any(item and item.get("section") != section for item in (before_item, after_item)):
        add("section_boundary", section, "邻近段落跨章节；核对本节前提，避免断章")
    if depth == "深入法义":
        add("specialist_review", depth, "请熟悉原典或讲记的审核人核对教义和上下文")
    add("keyword_only_theme_match", ", ".join(hits), "关键词命中不证明语义相关；人工核对主题、读者与完整语境")
    return risks


def passages(path):
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("检索 PDF 需要可选依赖 pypdf；扫描版还需先 OCR") from exc
        for page_no, page in enumerate(PdfReader(str(path)).pages, 1):
            text = page.extract_text() or ""
            if len(text.strip()) < 20:
                yield {"text": "", "locator": f"page {page_no}", "warning": "PDF 页面无可靠可检索文字；需 OCR 与人工核页"}
            else:
                for paragraph in re.split(r"\n\s*\n", text):
                    if paragraph.strip():
                        yield {"text": paragraph.strip(), "locator": f"page {page_no}"}
        return
    content = path.read_text(encoding="utf-8-sig")
    heading, lines, start_line = "", [], 1
    is_markdown = path.suffix.lower() in (".md", ".markdown")
    # ATX headings delimit paragraphs even without surrounding blank lines.
    for number, line in enumerate(content.splitlines() + [""], 1):
        title = re.match(r"^ {0,3}#{1,6}(?:[ \t]+|$)(.*)$", line) if is_markdown else None
        if title or not line.strip():
            if lines:
                yield {"text": "\n".join(lines).strip(), "locator": f"line {start_line}", "section": heading}
                lines = []
            if title:
                heading = re.sub(r"[ \t]+#+[ \t]*$", "", title.group(1)).strip()
        else:
            if not lines:
                start_line = number
            lines.append(line)


def selected_files(config, scope, max_files, max_bytes, base_dir=None):
    roots = config.get("paths", {})
    count = 0
    for group in scope:
        entries = roots.get(group) or []
        if isinstance(entries, str):
            entries = [entries]
        if not entries:
            raise ValueError(f"主题资料范围 {group} 未配置路径；请先在个人配置中填写")
        for entry in entries:
            root = resolve_path(entry, base_dir)
            if not root.exists():
                raise FileNotFoundError(f"{group} 路径不可用：{root}")
            files = [root] if root.is_file() else root.rglob("*")
            for path in files:
                if not path.is_file():
                    continue
                count += 1
                if count > max_files:
                    raise ValueError("达到文件数上限；请缩小资料路径或提高 --max-files")
                if path.suffix.lower() not in ALLOWED:
                    yield group, path, "unsupported_format"
                    continue
                if path.stat().st_size > max_bytes:
                    yield group, path, "file_too_large"
                    continue
                yield group, path, None


def search(config, themes, theme_id, max_files=500, max_bytes=20_000_000, max_results=30, base_dir=None):
    theme = next((x for x in themes["themes"] if x.get("id") == theme_id), None)
    if not theme or not theme.get("enabled", False):
        raise ValueError("主题不存在或已停用")
    keywords = [str(x).casefold() for x in theme.get("keywords", []) if str(x).strip()]
    if not keywords:
        raise ValueError("主题至少需要一个关键词")
    if not theme.get("source_scope"):
        raise ValueError("主题须指定资料范围；不能在空范围内报告检索完成")
    excludes = [str(x).casefold() for x in theme.get("exclude_keywords", [])]
    found, warnings, seen = [], [], {}
    files_scanned = 0
    skipped = 0
    duplicates_skipped = 0
    for group, path, skip_reason in selected_files(config, theme.get("source_scope", []), max_files, max_bytes, base_dir):
        if skip_reason:
            skipped += 1
            warnings.append({"file": str(path), "warning": skip_reason})
            continue
        source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            all_passages = list(passages(path))
        except UnicodeError:
            skipped += 1
            warnings.append({"file": str(path), "warning": "text_encoding_unreadable; convert to UTF-8 before searching"})
            continue
        files_scanned += 1
        for position, item in enumerate(all_passages):
            if item.get("warning"):
                warnings.append({"file": str(path), "locator": item["locator"], "warning": item["warning"]})
                continue
            original = item["text"]
            folded = original.casefold()
            hits = [term for term in keywords if term in folded]
            if not hits or any(term in folded for term in excludes):
                continue
            fingerprint = hashlib.sha256(re.sub(r"\s+", "", original).encode("utf-8")).hexdigest()
            if fingerprint in seen:
                duplicates_skipped += 1
                warnings.append({"file": str(path), "locator": item["locator"],
                                 "warning": "duplicate_text", "same_text_as": seen[fingerprint]})
                continue
            seen[fingerprint] = {"file": str(path), "locator": item["locator"]}
            before_item = next((p for p in reversed(all_passages[:position]) if p.get("text")), None)
            after_item = next((p for p in all_passages[position+1:] if p.get("text")), None)
            before = before_item["text"] if before_item else ""
            after = after_item["text"] if after_item else ""
            section = item.get("section")
            risk_checks = candidate_risks(original, before_item, after_item, section, hits, theme.get("depth"))
            flags = [check["action"] for check in risk_checks]
            found.append({"source_group": group, "file": str(path), "version": path.stat().st_mtime_ns,
                          "locator": item["locator"], "section": item.get("section", ""),
                          "original_exact": original, "source_sha256": source_sha,
                          "context_before": before[:1200], "context_after": after[:1200],
                          "context_before_locator": before_item.get("locator") if before_item else None,
                          "context_after_locator": after_item.get("locator") if after_item else None,
                          "context_note": "仅邻近段落线索；核对完整原文后再批准",
                          "theme_id": theme_id, "matched_keywords": hits, "recommendation": "原文命中主题关键词；须人工判断语义、完整上下文和适用性",
                          "risk_checks": risk_checks, "review_flags": flags, "approval": "pending_human_review"})
            if len(found) >= max_results:
                return {"theme": theme, "files_scanned": files_scanned, "files_skipped": skipped,
                        "duplicates_skipped": duplicates_skipped,
                        "results": found, "warnings": warnings,
                        "coverage": "命中结果达到上限；未宣称扫描完全部资料"}
    return {"theme": theme, "files_scanned": files_scanned, "files_skipped": skipped,
            "duplicates_skipped": duplicates_skipped,
            "results": found, "warnings": warnings,
            "coverage": "已检查指定范围内的文件；不支持或过大的文件列在 warnings，未纳入候选"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--themes", required=True)
    parser.add_argument("--theme-id", required=True)
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--max-bytes", type=int, default=20_000_000)
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if min(args.max_files, args.max_bytes, args.max_results) < 1:
        parser.error("上限必须为正数")
    result = search(json.loads(Path(args.config).expanduser().read_text(encoding="utf-8")),
                    json.loads(Path(args.themes).read_text(encoding="utf-8")), args.theme_id,
                    args.max_files, args.max_bytes, args.max_results,
                    Path(args.config).expanduser().resolve().parent)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"results": len(result["results"]), "files_scanned": result["files_scanned"], "coverage": result["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
