#!/usr/bin/env python3
"""Draft title, description, tags and cover text from an approved translation."""
import argparse
import json
from pathlib import Path

from translation_review import gemini_json, load, verify_approval, write_new


def draft(version, approval, model, provider=gemini_json):
    verified = verify_approval(version, approval)
    source = version["source"]["original_exact"]
    target = version["translation"]
    prompt = ("根据已批准的视频文案，为私密审片准备标题、简介、tags、封面文字候选。"
              "只从提供文字推导，不能补造教义、人物身份或功效；不要写发布承诺。"
              "返回 JSON：{\"title\":\"...\",\"description\":\"...\",\"tags\":[\"...\"],\"cover_text\":\"...\"}。"
              "\n原文：\n" + source + "\n已批准译文：\n" + target)
    prompt += "\n所有发布文字使用目标语种：" + version.get('target_language', '与已批准译文相同')
    response = provider(prompt, model)
    if not all(isinstance(response.get(k), str) and response[k].strip()
               for k in ("title", "description", "cover_text")):
        raise ValueError("发布资料缺标题、简介或封面文字")
    tags = response.get("tags")
    if not isinstance(tags, list) or any(not isinstance(x, str) or not x.strip() for x in tags):
        raise ValueError("tags 格式无效")
    return {"status": "pending_human_review", "version": verified["version"],
            "translation_sha256": verified["translation_sha256"], "model": model,
            "version_sha256": verified["version_sha256"],
            "title": response["title"].strip(), "description": response["description"].strip(),
            "tags": [x.strip() for x in tags], "cover_text": response["cover_text"].strip(),
            "review_note": "逐项核对成片内容、宗教/事实表述、标题和封面文字；封面图另行制作并复核"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--approval", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--confirm-external", action="store_true")
    a = p.parse_args()
    if not a.confirm_external:
        p.error("将向模型发送原文和译文；需明确 --confirm-external")
    write_new(a.out, draft(load(a.version), load(a.approval), a.model))
    print(json.dumps({"file": str(Path(a.out).resolve()), "status": "pending_human_review"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
