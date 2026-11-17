"""Render T1–T4 using supplied review-template layout and shared receipt protocol."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
from urllib.parse import urlsplit

from review_protocol import validate_round
from translation_review import version_digest

ASSETS = Path(__file__).resolve().parents[1] / "templates/reviews"
TITLES = {"T1": "中文原文与制作稿深审", "T2": "翻译与回译批量审核", "T3": "标题、封面文字与简介", "T4": "成片审核"}


def field(label, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return f"<p><b>{escape(label)}</b></p><pre>{escape(str(value if value is not None else '未提供'))}</pre>"


def mapping_html(value):
    keys = ("A_start", "A_end", "B_start", "B_end")
    if not isinstance(value, list) or not value or any(
            not isinstance(row, dict) or not isinstance(row.get("text"), str)
            or any(type(row.get(k)) is not int for k in keys) for row in value):
        return field("A→B 改动及位置", value)
    rows = ''.join('<tr><td>' + escape(row['text']) + '</td><td>' +
                   f"{row['A_start'] + 1}–{row['A_end']}" + '</td><td>' +
                   f"{row['B_start'] + 1}–{row['B_end']}" + '</td></tr>' for row in value)
    return ('<p><b>A→B 逐句对应（字符位置从1开始）</b></p><div style="overflow-x:auto">'
            '<table><thead><tr><th>原句</th><th>A位置</th><th>B位置</th></tr></thead><tbody>' + rows + '</tbody></table></div>')


def verify_source(source):
    """Verify an exact character range against a local UTF-8 source, never infer proof."""
    if source.get('kind') == 'sqlite_paragraph':
        from source_index import verify_index_source
        verify_index_source(source)
        return
    raw = Path(source["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("source file hash changed")
    text = raw.decode("utf-8-sig")
    start, end = source["start"], source["end"]
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
            or text[start:end] != source["original_exact"]):
        raise ValueError("source excerpt mismatch")
    if not source.get("locator"):
        raise ValueError("source locator missing")


def content_html(stage, item):
    c = item["content"]
    if stage in ("T1", "T2"):
        verify_source(c["source"])
    if stage == "T1":
        if c.get("A") != c["source"]["original_exact"]:
            raise ValueError("A must equal original source")
        body = '<div class="columns"><section class="column">' + field("A｜原文", c["A"])
        body += '</section><section class="column">' + field("B｜制作稿", c.get("B")) + '</section></div>'
        body += mapping_html(c.get("mapping"))
        for key, label in (("hook_mode", "钩子方案（不默认叠加）"), ("duration", "时长依据"), ("warnings", "必须复核的限制与时长提示")):
            body += field(label, c.get(key))
    elif stage == "T2":
        body = field("终版译文", c.get("translation")) + field("字数/时长与估算依据", c.get("duration"))
        body += '<details><summary>译审证据</summary>'
        for key, label in (("original", "中文制作稿"), ("draft", "初译"), ("backtranslation_provider", "实际盲回译提供方"),
                           ("backtranslation", "盲回译"), ("independent_provider", "实际独立校译提供方"),
                           ("independent_translation", "独立译"), ("differences", "差异"), ("reasoning", "判断依据"),
                           ("numbers", "数字核对"), ("terms", "术语核对")):
            body += field(label, c.get(key))
        body += '</details>'
    elif stage == "T3":
        body = "".join(field(label, c.get(key)) for key, label in (("title", "标题"), ("cover_text", "封面文字"),
                ("description", "简介"), ("tags", "标签"), ("body_evidence", "正文回应依据")))
        body += '<p>本次仅审核文字，不代表封面图片已选、成片通过或允许付费生成。</p>'
    else:
        body = field("成片信息", c.get("video")) + field("时长", c.get("duration"))
        if isinstance(c.get('video'), dict) and c['video'].get('path') and c['video'].get('sha256'):
            body += (f'<video data-local-review-video="{escape(item["id"], quote=True)}" controls '
                     'preload="metadata" playsinline style="width:100%;max-height:70vh;background:#111">'
                     '请通过本地审核服务打开以播放当前绑定成片。</video>'
                     '<p>本地播放需要审核服务在线；播放或拖动进度不代表审核通过。</p>')
        for key, label in (("video_url", "打开成片"), ("cover_url", "查看封面")):
            url = c.get(key, "")
            if url and urlsplit(url).scheme in ("https", "http"):
                body += f'<p><a rel="noreferrer" target="_blank" href="{escape(url, quote=True)}">{label}</a></p>'
        body += '<p>通过只确认当前成片；上传和公开发布仍按各自授权。</p>'
    if stage in ("T1", "T2"):
        s = c["source"]
        body += '<details><summary>来源、前后文与程序核验</summary>'
        for key in ("locator", "original_exact", "context_before", "context_after", "sha256"):
            body += field(key, s.get(key))
        proof = ('本次核对索引段落及同章节前后文哈希；未逐字核验原始 EPUB。'
                 if s.get('kind') == 'sqlite_paragraph' else '本次渲染已核对源文件哈希及指定范围逐字一致。')
        body += '<p>' + proof + '不代表语义或音画已审核。</p></details>'
    return body


def render(current):
    binding = validate_round(current)
    cards = []
    client = {k: current[k] for k in ("schema_version", "round_id", "task_id", "stage", "language", "version", "entry")}
    client.update(content_sha256=binding, items=[])
    for n, item in enumerate(current["items"]):
        card = f'<section class="item" data-index="{n}"><h2>{escape(item["id"])} · {escape(item["version"])}</h2>'
        card += content_html(current["stage"], item)
        for check in item["required_checks"]:
            card += f'<label class="check"><input type="checkbox" data-check="{escape(check, quote=True)}"> {escape(check)}</label>'
        if item["approval_blockers"]:
            card += field("尚未完成，不能通过", item["approval_blockers"])
        card += '<select data-decision><option value="pending">待审核</option><option value="approved">通过</option><option value="needs_changes">需修改</option></select>'
        if current["stage"] == "T1":
            card += '<select data-selection><option value="">请选择 A 或 B</option><option value="A">A 原文</option><option value="B">B 制作稿</option></select>'
        card += '<textarea class="anno" data-comment placeholder="逐条意见；需修改时必填"></textarea></section>'
        cards.append(card)
        client["items"].append({"id": item["id"], "version": item["version"], "content_sha256": version_digest(item),
                                "required_checks": item["required_checks"], "approval_blockers": item["approval_blockers"]})
    safe_json = json.dumps(client, ensure_ascii=False).replace("<", "\\u003c")
    title = TITLES[current["stage"]]
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title}</title><style>{(ASSETS / "review.css").read_text()}</style></head><body><main>'
            f'<h1>{title}</h1><p>{escape(current["task_id"])} · {escape(current["language"])} · {escape(current["version"])}</p>'
            '<p>逐条查看后选择结论。通过项完成核对，需修改项写明意见；未审条目保持待审核。审核结论与处理状态分开记录。</p>'
            + "".join(cards) + '<section class="submit"><button id="submit" type="button">提交本轮</button>'
            '<button id="refresh" type="button" class="secondary" disabled>查看处理状态</button>'
            '<button id="download" type="button" class="secondary">下载收据（备用）</button><p id="status" class="status">待提交</p></section>'
            f'<script id="review-data" type="application/json">{safe_json}</script><script>{(ASSETS / "review.js").read_text()}</script></main></body></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    page = render(json.loads(Path(args.round).read_text()))
    with Path(args.out).open("x", encoding="utf-8") as stream:
        stream.write(page)


if __name__ == "__main__":
    main()
