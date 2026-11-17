#!/usr/bin/env python3
"""Versioned translation, independent review, blind backtranslation, human decisions."""
import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from glossary_tools import select as select_glossary
from google_backtranslation import backtranslate as google_backtranslate, preflight as backtranslation_preflight

SPOKEN_RULE = "口播使用可直接朗读的自然目标语，不用中英文括号插入解释；必要含义写成自然口语，仅供查阅的术语释义放在审稿备注。保留否定、限定语与原意。"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def version_digest(version):
    return sha(json.dumps(version, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_stage(stage, prompt, model, workdir, provider= None, retry_unknown=False):
    provider = provider or gemini_json
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    intent_path = workdir / (stage + ".intent.json")
    result_path = workdir / (stage + ".result.json")
    binding = {"stage": stage, "model": model, "prompt_sha256": sha(prompt)}
    if result_path.exists():
        saved = load(result_path)
        if any(saved.get(key) != value for key, value in binding.items()):
            raise ValueError("模型阶段结果与本次稿件/模型不一致；使用新输出目录")
        return saved["response"]
    if intent_path.exists():
        intent = load(intent_path)
        if any(intent.get(key) != value for key, value in binding.items()):
            raise ValueError("模型阶段意图与本次稿件/模型不一致；使用新输出目录")
        if not retry_unknown:
            raise RuntimeError("已有结果未知的模型请求；先核查服务商结果，再显式 --retry-unknown")
    else:
        write_new(intent_path, {**binding, "status": "submitted_outcome_unknown", "at": now()})
    response = provider(prompt, model)
    write_new(result_path, {**binding, "response": response, "status": "completed", "at": now()})
    return response


def gemini_json(prompt, model, endpoint="https://generativelanguage.googleapis.com/v1beta", timeout=90):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("缺 GEMINI_API_KEY；密钥只应留在本机环境")
    if not model or "/" in model or ":" in model:
        raise ValueError("模型名无效")
    if endpoint != "https://generativelanguage.googleapis.com/v1beta":
        raise ValueError("此适配器只允许官方 Gemini API；其他服务需独立适配")
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    request = urllib.request.Request(endpoint + "/models/" + model + ":generateContent",
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.load(response)
            text = "\n".join(part["text"] for candidate in body.get("candidates", [])
                             for part in candidate.get("content", {}).get("parts", []) if "text" in part)
            if not text:
                raise ValueError("模型未返回正文")
            return json.loads(text)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise RuntimeError("模型调用结果不确定；保留本地任务状态，人工核实后再决定是否重试") from exc
            time.sleep(2 ** attempt)


def items_by_id(data, ids, field):
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("模型输出缺 items")
    found = {}
    for item in items:
        key = str(item.get("id", ""))
        if key in found or not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError("模型输出重复 ID 或正文为空")
        found[key] = item[field].strip()
    if set(found) != set(ids):
        raise ValueError("模型输出 ID 与输入不一致")
    return found


def model_config_for_source(model_config, source, target_language, project_config=None, previous=None):
    result = dict(model_config)
    inline = result.get("glossary", [])
    if not isinstance(inline, list) or len(inline) > 100:
        raise ValueError("模型配置的 glossary 须为不超过 100 条的列表")
    selected_inline = []
    for item in inline:
        if isinstance(item, dict):
            source_term, target_term = str(item.get("source") or "").strip(), str(item.get("target") or "").strip()
            if not source_term or not target_term:
                raise ValueError("模型配置中的术语对象须有 source 与 target")
            if source_term.casefold() in source["original_exact"].casefold():
                selected_inline.append(item)
        elif isinstance(item, str) and item.strip() and len(item) <= 500:
            selected_inline.append(item.strip())
        else:
            raise ValueError("模型配置的 glossary 条目须为术语对象或短文字")
    if project_config:
        matched = select_glossary(load(project_config), source["original_exact"], target_language,
                                  Path(project_config).expanduser().resolve().parent)
        for item in selected_inline:
            if isinstance(item, dict) and any(item["source"].casefold() == term["source"].casefold()
                                              and item["target"] != term["target"] for term in matched):
                raise ValueError("模型配置与项目术语表对同一术语给出冲突译法：" + item["source"])
        result["glossary"] = [*selected_inline, *matched]
    elif previous and any(isinstance(item, dict) and item.get("source_file")
                          for item in previous.get("glossary", [])):
        raise ValueError("上一版使用项目术语表；返修须传 --project-config 重新核对当前术语")
    else:
        result["glossary"] = selected_inline
    return result


def prompt_terms(glossary):
    """Keep local file paths and hashes in the version, never in model prompts."""
    result = []
    for item in glossary:
        if isinstance(item, dict):
            result.append({key: item[key] for key in ("source", "target", "language", "note")
                           if key in item and item[key]})
        else:
            result.append(item)
    return json.dumps(result, ensure_ascii=False)


def temporary_gemini_backtranslation(target, language, model, consent, stage_call):
    """One invocation only; caller records the user's explicit choice, not approval."""
    if not consent or not consent.strip():
        raise ValueError("临时 Gemini 回译需要本次用户明确同意的原话或引用")
    prompt = ("仅将以下目标语正文盲回译为中文，不添加解释。"
              '只返回 JSON {"items":[{"id":"1","translation":"..."}]}。正文：\n' + target)
    result = stage_call("backtranslation_gemini_temporary", prompt, model)
    text = items_by_id(result, ["1"], "translation")["1"]
    return {"text": text, "provider": "gemini", "model": model,
            "temporary": True, "user_consent": consent.strip(),
            "target_language": language, "target_sha256": sha(target)}


def backtranslation_setup_needed(config):
    try:
        backtranslation_preflight(config)
    except ValueError as exc:
        return {"state": "needs_backtranslation_choice", "reason": str(exc),
                "message": "请引导补齐 Google 回译配置；也可询问是否本次临时使用 Gemini 回译。未经同意不替换提供方。",
                "options": ["configure_google_translate", "continue_other_steps", "ask_temporary_gemini"],
                "existing_results_preserved": True, "other_steps_available": True,
                "model_calls": 0, "review_completed": False}
    return None


def create_item(source, target_language, model_config, provider=gemini_json, stage_call=None, draft=None, draft_author=None, backtranslation_call=None):
    if backtranslation_call is None:
        backtranslation_preflight(model_config)
    if not source.get("original_exact") or not source.get("file") or not source.get("locator"):
        raise ValueError("缺原文或可核查出处")
    original = source["original_exact"]
    if draft is not None:
        if not draft_author or not draft_author.strip():
            raise ValueError("传入初译须注明真实来源，如 Codex 或人工译者")
        return make_version(source, target_language, draft, model_config, provider,
                            translation_model=draft_author.strip(), stage_call=stage_call, backtranslation_call=backtranslation_call)
    glossary = model_config.get("glossary", [])
    translation_model = model_config["translation_model"]
    review_model = model_config["review_model"]
    call = stage_call or (lambda stage, prompt, model: provider(prompt, model))
    tr = call("translation", "将以下中文原文译为 " + target_language + "，保留数字、专名和含义。" + SPOKEN_RULE + "术语参考：" + prompt_terms(glossary) + "。只返回 JSON {\"items\":[{\"id\":\"1\",\"translation\":\"...\"}]}。原文：\n" + original, translation_model)
    target = items_by_id(tr, ["1"], "translation")["1"]
    return make_version(source, target_language, target, model_config, provider,
                        translation_model=translation_model, stage_call=stage_call, backtranslation_call=backtranslation_call)


def make_version(source, target_language, target, model_config, provider=gemini_json, translation_model=None, previous=None, feedback_response=None, stage_call=None, backtranslation_call=None):
    if backtranslation_call is None:
        backtranslation_preflight(model_config)
    if not target.strip():
        raise ValueError("译稿为空")
    original = source["original_exact"]
    review_model = model_config["review_model"]
    glossary = model_config.get("glossary", [])
    call = stage_call or (lambda stage, prompt, model: provider(prompt, model))
    independent_prompt = ("独立翻译以下中文原文为 " + target_language +
                          "；此步骤不要参考已有译稿。" + SPOKEN_RULE + "术语参考：" + prompt_terms(glossary) +
                          "。只返回 JSON {\"items\":[{\"id\":\"1\",\"translation\":\"...\"}]}。中文原文：\n" + original)
    independent = items_by_id(call("independent_translation", independent_prompt, review_model),
                              ["1"], "translation")["1"]
    # This service receives target only. Gemini independently translates/reviews.
    back_evidence = (backtranslation_call or google_backtranslate)(target, target_language)
    back = back_evidence.get("text")
    actual_provider = back_evidence.get("provider")
    temporary_gemini = (actual_provider == "gemini" and back_evidence.get("temporary") is True
                        and isinstance(back_evidence.get("user_consent"), str)
                        and bool(back_evidence["user_consent"].strip()))
    if not isinstance(back, str) or not back.strip() or not (actual_provider == "google_translate" or temporary_gemini):
        raise ValueError("盲回译证据缺失，或 Gemini 临时回译缺本次用户同意记录")
    review_prompt = "你是独立译审。先前你仅根据中文原文给出的独立译文如下；现在比较原文、当前译稿与独立译文，指出漏译、增译、误义和术语问题。不要自称人工批准。只返回 JSON {\"items\":[{\"id\":\"1\",\"review\":\"...\"}]}。术语参考：" + prompt_terms(glossary) + "\n中文原文：\n" + original + "\n当前译稿：\n" + target + "\n独立译文：\n" + independent
    review_prompt += "\n口播检查：" + SPOKEN_RULE + "发现括号解释时明确标记为需返修，不能直接删字冒充原稿已通过。"
    review = items_by_id(call("independent_review", review_prompt, review_model), ["1"], "review")["1"]
    number = 1 if previous is None else int(previous["version"]) + 1
    return {"version": number, "created_at": now(), "source": source,
            "target_language": target_language, "translation": target, "translation_sha256": sha(target),
            "blind_backtranslation": back, "independent_translation": independent,
            "independent_review": review,
            "models": {"translation": translation_model or "human_revision", "review": review_model,
                       "backtranslation": ("google-translate-nmt" if actual_provider == "google_translate"
                                           else "gemini:" + back_evidence["model"])}, "glossary": glossary,
            "backtranslation_evidence": back_evidence,
            "previous_version": None if previous is None else previous["version"],
            "feedback_response": feedback_response,
            "human_decision": "pending", "human_reviewer": None, "human_feedback": None}


def human_decision(version, reviewer, decision, feedback):
    if decision not in ("approve", "revise", "reject", "defer"):
        raise ValueError("人审结果必须明确为 approve/revise/reject/defer")
    if not reviewer.strip() or not feedback.strip():
        raise ValueError("需填写审核人及具体意见")
    if version.get("translation_sha256") != sha(version.get("translation", "")):
        raise ValueError("译文正文与版本哈希不符")
    if decision == "approve" and any(not str(version.get(field, "")).strip() for field in
                                     ("independent_translation", "blind_backtranslation", "independent_review")):
        raise ValueError("批准前须有独立译文、盲回译和对照复核；旧版需重做译审")
    return {"version": version["version"], "translation_sha256": version["translation_sha256"],
            "version_sha256": version_digest(version),
            "reviewer": reviewer, "decision": decision, "feedback": feedback, "at": now(),
            "attestation": "由操作人输入；程序不能独立证明其身份"}


def verify_approval(version, decision):
    if (any(not str(version.get(field, "")).strip() for field in
            ("independent_translation", "blind_backtranslation", "independent_review"))
            or version.get("translation_sha256") != sha(version.get("translation", ""))
            or decision.get("decision") != "approve" or decision.get("version") != version.get("version")
            or decision.get("translation_sha256") != version.get("translation_sha256")
            or decision.get("version_sha256") != version_digest(version)):
        raise ValueError("当前译稿版本没有匹配的明确人工批准")
    return {"approved": True, "version": version["version"], "reviewer": decision["reviewer"],
            "translation_sha256": version["translation_sha256"], "version_sha256": version_digest(version)}


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--source", required=True, help="单条出处记录 JSON")
    create.add_argument("--language", required=True)
    create.add_argument("--models", required=True, help="私密模型/术语配置 JSON")
    create.add_argument("--draft", help="Codex 或用户已有初译 TXT；省去重新调用初译模型，仍执行 Gemini 独立复核")
    create.add_argument("--draft-author", help="初译实际来源；与 --draft 一起提供")
    create.add_argument("--project-config", help="本人包外项目配置；只读取 paths.glossary 中命中本条原文的术语")
    create.add_argument("--out", required=True)
    create.add_argument("--confirm-external", action="store_true")
    create.add_argument("--retry-unknown", action="store_true", help="人工核查后允许重新发出结果未知的模型请求")
    revise = sub.add_parser("revise")
    revise.add_argument("--previous", required=True)
    revise.add_argument("--text", required=True)
    revise.add_argument("--models", required=True)
    revise.add_argument("--project-config", help="上一版使用项目术语表时必须重新提供，避免沿用过期术语")
    revise.add_argument("--previous-decision", required=True, help="上一版的人审记录")
    revise.add_argument("--feedback-response", required=True, help="逐条说明如何处理上一版意见")
    revise.add_argument("--out", required=True)
    revise.add_argument("--confirm-external", action="store_true")
    revise.add_argument("--retry-unknown", action="store_true", help="人工核查后允许重新发出结果未知的模型请求")
    for command in (create, revise):
        command.add_argument("--temporary-gemini-backtranslation", action="store_true",
                             help="仅本次使用 Gemini 回译，须先取得用户明确同意")
        command.add_argument("--backtranslation-consent", help="本次用户同意原话或可核查引用")
    decide = sub.add_parser("decide")
    decide.add_argument("--version", required=True)
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--decision", required=True, choices=("approve", "revise", "reject", "defer"))
    decide.add_argument("--feedback", required=True)
    decide.add_argument("--out", required=True)
    verify = sub.add_parser("verify-approved")
    verify.add_argument("--version", required=True)
    verify.add_argument("--decision", required=True)
    args = p.parse_args()
    if args.command in ("create", "revise") and not args.confirm_external:
        p.error("模型调用会发送资料到服务商；需明确 --confirm-external")
    if args.command in ("create", "revise"):
        raw_models = load(args.models)
        if args.temporary_gemini_backtranslation:
            if not args.backtranslation_consent or not args.backtranslation_consent.strip():
                p.error("须先询问用户并用 --backtranslation-consent 记录本次同意，不能代填")
        elif args.backtranslation_consent:
            p.error("同意记录须与 --temporary-gemini-backtranslation 一起使用")
        else:
            pending = backtranslation_setup_needed(raw_models)
            if pending:
                print(json.dumps(pending, ensure_ascii=False))
                return
        stage_dir = Path(args.out).with_suffix(Path(args.out).suffix + ".stages")
        stage_call = lambda stage, prompt, model: model_stage(
            stage, prompt, model, stage_dir, retry_unknown=args.retry_unknown)
        if args.temporary_gemini_backtranslation:
            model = raw_models.get("backtranslation_model")
            if not model or model == "nmt":
                model = raw_models["review_model"]
            backtranslation_call = lambda target, language: temporary_gemini_backtranslation(
                target, language, model, args.backtranslation_consent, stage_call)
        else:
            backtranslation_call = lambda target, language: google_backtranslate(
                target, language, workdir=stage_dir, retry_unknown=args.retry_unknown)
    if args.command == "create":
        source = load(args.source)
        models = model_config_for_source(load(args.models), source, args.language, args.project_config)
        draft = Path(args.draft).read_text(encoding='utf-8-sig') if args.draft else None
        if bool(args.draft) != bool(args.draft_author):
            p.error('--draft 与 --draft-author 须一起提供')
        result = create_item(source, args.language, models, stage_call=stage_call,
                             draft=draft, draft_author=args.draft_author, backtranslation_call=backtranslation_call)
    elif args.command == "revise":
        previous = load(args.previous)
        prior_decision = load(args.previous_decision)
        if (prior_decision.get("version") != previous.get("version") or
                prior_decision.get("translation_sha256") != previous.get("translation_sha256") or
                prior_decision.get("version_sha256") != version_digest(previous)):
            raise ValueError("上一版审稿意见与译稿版本不符")
        target = Path(args.text).read_text(encoding="utf-8")
        models = model_config_for_source(load(args.models), previous["source"], previous["target_language"],
                                         args.project_config, previous)
        result = make_version(previous["source"], previous["target_language"], target,
                              models, previous=previous,
                              feedback_response={"previous_feedback": prior_decision.get("feedback"),
                                                 "response": args.feedback_response}, stage_call=stage_call,
                              backtranslation_call=backtranslation_call)
    elif args.command == "decide":
        result = human_decision(load(args.version), args.reviewer, args.decision, args.feedback)
    else:
        print(json.dumps(verify_approval(load(args.version), load(args.decision)), ensure_ascii=False))
        return
    write_new(args.out, result)
    print(json.dumps({"file": str(Path(args.out).resolve()), "version": result["version"],
                      "decision": result.get("decision", result.get("human_decision"))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
