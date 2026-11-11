#!/usr/bin/env python3
"""Portable HeyGen asset upload, translation submission, status and download.

Uses official v3 endpoints. Paid submission is an explicit separate command.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import quote
from paid_authorization import claim as claim_paid, create_scope, generate_scope, verify as verify_paid

API = "https://api.heygen.com/v3"


def auth_check(key, expected_email=None):
    """Check this script's API-key channel without creating an asset or job."""
    data = request_json("GET", "/users/me", key).get("data") or {}
    if not data.get("username") and not data.get("email"):
        raise ValueError("HeyGen 未返回可识别的账号")
    email = data.get("email")
    if expected_email and (not email or email.casefold() != expected_email.casefold()):
        raise ValueError("API Key 所属账号与 --expected-email 不一致；当前账号：" + str(email or "未返回邮箱"))
    return {"status": "authenticated", "transport": "direct_api_key",
            "account_email": email,
            "expected_account_verified": bool(expected_email),
            "account_fingerprint": hashlib.sha256(
                str(data.get("username") or data.get("email")).encode()).hexdigest()[:12],
            "billing_type": data.get("billing_type"),
            "upload_permission": "not_verified", "proofread_permission": "not_verified"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def request_json(method, endpoint, key, **kwargs):
    import requests
    headers = {"x-api-key": key}
    for attempt in range(3):
        try:
            response = requests.request(method, API + endpoint, headers=headers, timeout=(15, 120), **kwargs)
            if response.status_code in (429, 500, 502, 503, 504) and method == "GET" and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if method != "GET" or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def validate_preflight(preflight, file_path=None):
    data = json.loads(Path(preflight).read_text(encoding="utf-8"))
    if data.get("status") != "ready_for_review" or data.get("purpose") != "estimated_pre_heygen_timeline_not_final_audio_alignment":
        raise ValueError("缺少通过的语速与视频时长预检")
    if file_path and data.get("clip_sha256") != digest(file_path):
        raise ValueError("预检绑定的视频哈希与待上传文件不一致")
    return data


def validate_asset_binding(payload, preflight, asset_receipt):
    report = validate_preflight(preflight)
    asset = json.loads(Path(asset_receipt).read_text(encoding="utf-8"))
    if (asset.get("status") != "uploaded" or asset.get("sha256") != report.get("clip_sha256")
            or payload.get("video") != {"type": "asset_id", "asset_id": asset.get("asset_id")}):
        raise ValueError("HeyGen 视频资产与预检/提交配置不一致")
    return report


def asset_upload(path, key, receipt, preflight=None):
    # A POST with uncertain outcome must be reconciled manually, never retried blindly.
    import requests
    from requests_toolbelt.multipart.encoder import MultipartEncoder
    path = Path(path)
    if path.suffix.lower() in (".mp4", ".mov", ".webm"):
        if not preflight: raise ValueError("视频上传前须提供 --preflight")
        validate_preflight(preflight, path)
    save_new(receipt, {"operation": "asset_upload", "status": "submitted_outcome_unknown",
                       "file_name": path.name, "sha256": digest(path)})
    with path.open("rb") as f:
        body = MultipartEncoder(fields={"file": (path.name, f, "application/octet-stream")})
        response = requests.post(API + "/assets", headers={"x-api-key": key, "Content-Type": body.content_type},
                                 data=body, timeout=(15, 600))
    response.raise_for_status()
    data = response.json().get("data") or {}
    if not data.get("asset_id"):
        raise ValueError("HeyGen 未返回 asset_id；请核对远端资产，勿直接重传")
    result = {"operation": "asset_upload", "status": "uploaded", "asset_id": data["asset_id"],
              "file_name": path.name, "sha256": digest(path)}
    save_new(str(receipt) + ".result.json", result)
    return result


def validate_translation(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("video"), dict):
        raise ValueError("提交 JSON 需要 video 对象")
    video = payload["video"]
    if video.get("type") not in ("asset_id", "url") or not video.get(video["type"]):
        raise ValueError("video 必须含有效 asset_id 或 url")
    if not payload.get("output_languages") or not all(isinstance(x, str) and x for x in payload["output_languages"]):
        raise ValueError("需要 output_languages")
    if payload.get("mode", "speed") not in ("speed", "precision"):
        raise ValueError("mode 仅支持 speed/precision")
    if payload.get("translate_audio_only") is not False:
        raise ValueError("口型视频须显式设置 translate_audio_only=false")


def submit_translation(payload, key, receipt, preflight=None, asset_receipt=None,
                       paid_authorization=None, paid_scope=None):
    validate_translation(payload)
    if not preflight or not asset_receipt:
        raise ValueError("提交前须提供 --preflight 与 --asset-receipt")
    validate_asset_binding(payload, preflight, asset_receipt)
    if payload.get("enable_dynamic_duration") is not True:
        raise ValueError("直译提交须显式设置 enable_dynamic_duration=true")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if paid_authorization:
        claim_paid(paid_authorization, paid_scope)
    save_new(receipt, {"operation": "translation_submit", "status": "submitted_outcome_unknown",
                       "request_sha256": fingerprint})
    response = request_json("POST", "/video-translations", key, json=payload)
    ids = (response.get("data") or {}).get("video_translation_ids") or []
    if not ids:
        raise ValueError("HeyGen 未返回任务 ID；请先查远端，勿重复提交")
    result = {"operation": "translation_submit", "status": "submitted", "request_sha256": fingerprint,
              "video_translation_ids": ids}
    save_new(str(receipt) + ".result.json", result)
    return result


def approved_target(version_path, decision_path, text_path, preflight, language=None):
    # Local import avoids a cycle: review_binding reuses this module's preflight checks.
    from review_binding import approved_preflight
    if not all((version_path, decision_path, text_path, preflight)):
        raise ValueError("API Proofread 须提供当前译稿、人审决定、逐句文案和语速预检")
    return approved_preflight(version_path, decision_path, text_path, preflight, language)


def create_proofread(payload, key, receipt, preflight, asset_receipt,
                     text_path=None, review_version=None, review_decision=None,
                     paid_authorization=None, paid_scope=None):
    validate_asset_binding(payload, preflight, asset_receipt)
    if (not payload.get("title") or not payload.get("output_languages")
            or payload.get("enable_video_stretching") is not True
            or payload.get("mode") not in ("speed", "precision")):
        raise ValueError("校对配置须含标题、语种、模式与 enable_video_stretching=true")
    if len(payload["output_languages"]) != 1:
        raise ValueError("API Proofread 每次仅提交一个已审目标语种")
    approved = approved_target(review_version, review_decision, text_path, preflight,
                               payload["output_languages"][0])
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if paid_authorization:
        claim_paid(paid_authorization, paid_scope)
    save_new(receipt, {"operation": "proofread_create", "status": "submitted_outcome_unknown",
                       "request_sha256": fingerprint,
                       "review_version_sha256": approved["version_sha256"]})
    response = request_json("POST", "/video-translations/proofreads", key, json=payload)
    ids = (response.get("data") or {}).get("proofread_ids") or []
    if not ids: raise ValueError("未返回 proofread_ids；先查远端，勿重复创建")
    result = {"operation": "proofread_create", "status": "created", "proofread_ids": ids,
              "request_sha256": fingerprint, "dynamic_duration_requested": True,
              "review_version_sha256": approved["version_sha256"]}
    save_new(str(receipt) + ".result.json", result)
    return result


def proofread_status(proofread_id, key):
    data = request_json("GET", "/video-translations/proofreads/" + quote(proofread_id, safe=""), key).get("data") or {}
    return {k: data.get(k) for k in ("id", "status", "output_language", "submitted_for_review", "failure_message")}


def proofread_srt(proofread_id, key, out):
    import requests
    data = request_json("GET", "/video-translations/proofreads/" + quote(proofread_id, safe="") + "/srt", key).get("data") or {}
    url = data.get("srt_url")
    if not url or urlparse(url).scheme != "https": raise ValueError("校对 SRT 链接无效")
    response = requests.get(url, timeout=(15, 120))
    response.raise_for_status()
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f: f.write(response.content)
    result = {"operation": "proofread_srt", "proofread_id": proofread_id, "file": str(path), "sha256": digest(path)}
    save_new(str(path) + ".receipt.json", result)
    return result


def update_proofread_srt(proofread_id, key, srt_asset_receipt, approved_srt, receipt,
                         text_path=None, preflight=None, review_version=None, review_decision=None):
    from subtitle_tools import full_text, normalized, parse_srt, read_text
    approved = approved_target(review_version, review_decision, text_path, preflight)
    if normalized(full_text(parse_srt(approved_srt))) != normalized(read_text(text_path)):
        raise ValueError("目标 SRT 与当前批准译稿不一致")
    asset = json.loads(Path(srt_asset_receipt).read_text(encoding="utf-8"))
    if asset.get("status") != "uploaded" or asset.get("sha256") != digest(approved_srt) or Path(approved_srt).suffix.lower() != ".srt":
        raise ValueError("已审 SRT 与上传资产回执不一致")
    save_new(receipt, {"operation": "proofread_srt_update", "status": "submitted_outcome_unknown",
                       "proofread_id": proofread_id, "srt_sha256": asset["sha256"],
                       "review_version_sha256": approved["version_sha256"]})
    request_json("PUT", "/video-translations/proofreads/" + quote(proofread_id, safe="") + "/srt", key,
                 json={"srt": {"type": "asset_id", "asset_id": asset["asset_id"]}})
    result = {"operation": "proofread_srt_update", "status": "updated", "proofread_id": proofread_id,
              "srt_sha256": asset["sha256"],
              "review_version_sha256": approved["version_sha256"]}
    save_new(str(receipt) + ".result.json", result)
    return result


def generate_proofread(proofread_id, key, approved_srt, update_receipt, roundtrip_srt, receipt,
                       text_path=None, preflight=None, review_version=None, review_decision=None,
                       paid_authorization=None, paid_scope=None):
    from subtitle_tools import full_text, normalized, parse_srt, read_text
    approved = approved_target(review_version, review_decision, text_path, preflight)
    if normalized(full_text(parse_srt(approved_srt))) != normalized(read_text(text_path)):
        raise ValueError("最终 SRT 与当前批准译稿不一致")
    update = json.loads(Path(update_receipt).read_text(encoding="utf-8"))
    if (update.get("status") != "updated" or update.get("proofread_id") != proofread_id
            or update.get("srt_sha256") != digest(approved_srt)
            or update.get("review_version_sha256") != approved["version_sha256"]):
        raise ValueError("最终生成前须核实已审 SRT 与更新回执")
    if Path(roundtrip_srt).read_bytes() != Path(approved_srt).read_bytes():
        raise ValueError("HeyGen 回读 SRT 与批准稿不一致")
    roundtrip = json.loads(Path(str(roundtrip_srt) + ".receipt.json").read_text(encoding="utf-8"))
    if (roundtrip.get("operation") != "proofread_srt" or roundtrip.get("proofread_id") != proofread_id
            or roundtrip.get("sha256") != digest(roundtrip_srt)):
        raise ValueError("缺少对应 Proofread 会话的回读回执")
    if paid_authorization:
        claim_paid(paid_authorization, paid_scope)
    save_new(receipt, {"operation": "proofread_generate", "status": "submitted_outcome_unknown",
                       "proofread_id": proofread_id, "srt_sha256": update["srt_sha256"],
                       "review_version_sha256": approved["version_sha256"]})
    response = request_json("POST", "/video-translations/proofreads/" + quote(proofread_id, safe="") + "/generate",
                            key, json={"translate_audio_only": False})
    data = response.get("data") or {}
    result = {"operation": "proofread_generate", "status": "submitted", "proofread_id": proofread_id,
              "response": {k: data.get(k) for k in ("video_translation_id", "video_translation_ids", "status")},
              "srt_sha256": update["srt_sha256"],
              "review_version_sha256": approved["version_sha256"]}
    save_new(str(receipt) + ".result.json", result)
    return result


def status(job_id, key):
    from urllib.parse import quote
    data = request_json("GET", "/video-translations/" + quote(job_id, safe=""), key).get("data") or {}
    return {k: data.get(k) for k in ("id", "status", "output_language", "video_url", "failure_message")}


def download(job_id, key, output):
    import requests
    info = status(job_id, key)
    url = info.get("video_url")
    if info.get("status") != "completed" or not url:
        raise ValueError("任务尚未完成或没有 video_url")
    if urlparse(url).scheme != "https":
        raise ValueError("仅下载 HTTPS 成片链接")
    output = Path(output)
    if output.exists():
        raise FileExistsError("输出已存在")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    if temporary.exists():
        raise FileExistsError("发现未完成下载；请核对后处理 .partial")
    try:
        with requests.get(url, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            with temporary.open("xb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
        if temporary.stat().st_size == 0:
            raise ValueError("下载结果为空")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    receipt = {"operation": "download", "status": "downloaded", "job_id": job_id,
               "file": str(output), "size_bytes": output.stat().st_size, "sha256": digest(output)}
    save_new(str(output) + ".receipt.json", receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("auth-check"); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("upload-asset"); a.add_argument("--file", required=True); a.add_argument("--receipt", required=True); a.add_argument("--preflight"); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("submit-translation"); a.add_argument("--payload", required=True); a.add_argument("--receipt", required=True); a.add_argument("--confirm-paid", action="store_true"); a.add_argument("--direct-no-proofread", action="store_true"); a.add_argument("--preflight", required=True); a.add_argument("--asset-receipt", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--paid-authorization", required=True)
    a = sub.add_parser("create-proofread"); a.add_argument("--payload", required=True); a.add_argument("--receipt", required=True); a.add_argument("--preflight", required=True); a.add_argument("--asset-receipt", required=True); a.add_argument("--confirm-paid", action="store_true"); a.add_argument("--text", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--paid-authorization", required=True)
    a = sub.add_parser("proofread-status"); a.add_argument("--proofread-id", required=True)
    a = sub.add_parser("proofread-srt"); a.add_argument("--proofread-id", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("proofread-update-srt"); a.add_argument("--proofread-id", required=True); a.add_argument("--approved-srt", required=True); a.add_argument("--srt-asset-receipt", required=True); a.add_argument("--receipt", required=True); a.add_argument("--text", required=True); a.add_argument("--preflight", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("generate-proofread"); a.add_argument("--proofread-id", required=True); a.add_argument("--approved-srt", required=True); a.add_argument("--update-receipt", required=True); a.add_argument("--roundtrip-srt", required=True); a.add_argument("--receipt", required=True); a.add_argument("--confirm-paid", action="store_true"); a.add_argument("--text", required=True); a.add_argument("--preflight", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--draft-receipt", required=True); a.add_argument("--paid-authorization", required=True)
    a = sub.add_parser("status"); a.add_argument("--job-id", required=True)
    a = sub.add_parser("download"); a.add_argument("--job-id", required=True); a.add_argument("--out", required=True)
    args = p.parse_args()
    key = os.environ.get("HEYGEN_API_KEY")
    if not key:
        p.error("需在当前设备设置 HEYGEN_API_KEY 环境变量")
    stage = "identity"
    try:
        if args.action in {"upload-asset", "submit-translation", "create-proofread", "proofread-update-srt", "generate-proofread"}:
            account = auth_check(key, args.expected_email)
        stage = "operation"
        if args.action == "auth-check": result = auth_check(key, args.expected_email)
        elif args.action == "upload-asset":
            if not Path(args.file).is_file(): raise FileNotFoundError(args.file)
            result = asset_upload(args.file, key, args.receipt, args.preflight)
        elif args.action == "submit-translation":
            if not args.confirm_paid or not args.direct_no_proofread: raise ValueError("直接生成须显式传 --confirm-paid --direct-no-proofread")
            scope = create_scope("api_key_direct_translation", args.expected_email, args.preflight, args.payload)
            verify_paid(args.paid_authorization, scope, account["billing_type"])
            result = submit_translation(json.loads(Path(args.payload).read_text(encoding="utf-8")), key, args.receipt, args.preflight, args.asset_receipt, args.paid_authorization, scope)
        elif args.action == "create-proofread":
            if not args.confirm_paid: raise ValueError("创建校对会话可能消耗额度，须显式传 --confirm-paid")
            scope = create_scope("api_key_proofread_create", args.expected_email, args.preflight, args.payload)
            verify_paid(args.paid_authorization, scope, account["billing_type"])
            result = create_proofread(json.loads(Path(args.payload).read_text(encoding="utf-8")), key, args.receipt, args.preflight, args.asset_receipt, args.text, args.review_version, args.review_decision, args.paid_authorization, scope)
            if len(result["proofread_ids"]) != 1:
                raise ValueError("API 未返回唯一 Proofread ID；先查询远端，不要重新提交")
            result.update({"proofread_id": result["proofread_ids"][0], "account_email": args.expected_email,
                           **{k: scope[k] for k in ("mode", "target_language", "clip_seconds", "clip_sha256",
                                                  "text_sha256", "request_sha256", "dynamic_duration_requested")}})
            Path(str(args.receipt) + ".result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.action == "proofread-status": result = proofread_status(args.proofread_id, key)
        elif args.action == "proofread-srt": result = proofread_srt(args.proofread_id, key, args.out)
        elif args.action == "proofread-update-srt":
            result = update_proofread_srt(args.proofread_id, key, args.srt_asset_receipt, args.approved_srt, args.receipt, args.text, args.preflight, args.review_version, args.review_decision)
        elif args.action == "generate-proofread":
            if not args.confirm_paid: raise ValueError("最终生成须显式传 --confirm-paid")
            scope = generate_scope("api_key_proofread_generate", args.expected_email,
                                   args.draft_receipt, args.approved_srt, args.proofread_id)
            verify_paid(args.paid_authorization, scope, account["billing_type"])
            result = generate_proofread(args.proofread_id, key, args.approved_srt, args.update_receipt, args.roundtrip_srt, args.receipt, args.text, args.preflight, args.review_version, args.review_decision, args.paid_authorization, scope)
        elif args.action == "status": result = status(args.job_id, key)
        else: result = download(args.job_id, key, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        # Never echo provider exceptions: URLs and response bodies may contain secrets.
        message = (str(exc) if (args.action == "auth-check" or stage == "identity") and isinstance(exc, ValueError)
                   else "请查看本次本地回执；远端结果未知时先查询，勿重复提交")
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "message": message}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
