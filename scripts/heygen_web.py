#!/usr/bin/env python3
"""Hand a HeyGen CLI OAuth proofread draft to a human web reviewer.

This deliberately stops at a draft. Final generation is a separate command.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from heygen_portable import digest, save_new, validate_asset_binding, validate_preflight
from subtitle_tools import full_text, normalized, parse_srt, read_text
from review_binding import approved_preflight
from translation_review import load as load_review, verify_approval
from paid_authorization import claim as claim_paid, create_scope, generate_scope, verify as verify_paid

ROOT = Path(__file__).resolve().parents[1]
MAX_SIMPLE_ASSET = 50 * 1000 * 1000


def cli_path():
    candidate = os.environ.get("HEYGEN_CLI") or str(ROOT / ".tools" / "bin" / "heygen")
    if Path(candidate).is_file():
        return candidate
    found = shutil.which("heygen")
    if found:
        return found
    raise FileNotFoundError("未安装 HeyGen CLI；先运行 ./install.sh heygen（Windows 在 WSL 中运行）")


def run_cli(args, timeout=180):
    if os.environ.get("HEYGEN_API_KEY"):
        raise ValueError("HEYGEN_API_KEY 会覆盖 CLI OAuth；请在当前终端取消该环境变量后重试")
    proc = subprocess.run([cli_path(), *args], text=True, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError("HeyGen CLI 调用失败；请用 heygen auth status 核对登录与账号，结果未知时先查远端")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("HeyGen CLI 未返回 JSON") from exc


def auth_check(expected_email):
    status = run_cli(["auth", "status"])
    credential = status.get("credential") or {}
    account = status.get("data") or {}
    if credential.get("type") != "oauth":
        raise ValueError("当前 HeyGen CLI 凭据不是 OAuth；运行 heygen auth login --oauth")
    email = account.get("email")
    if not email or email.casefold() != expected_email.casefold():
        raise ValueError("HeyGen CLI OAuth 登录账号不符；当前账号：" + str(email or "未返回邮箱"))
    return {"status": "authenticated", "credential_type": "oauth", "account_email": email,
            "billing_type": account.get("billing_type"), "expected_account_verified": True,
            "web_editor_access": "not_verified_by_auth_check"}


def upload_asset(path, preflight, expected_email, receipt):
    auth_check(expected_email)
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > MAX_SIMPLE_ASSET:
        raise ValueError("CLI 简单上传上限为 50 MB；请先压制适合上传的副本或使用经批准的 HTTPS 素材入口")
    validate_preflight(preflight, path)
    intent = {"operation": "cli_oauth_asset_upload", "status": "submitted_outcome_unknown",
              "sha256": digest(path), "idempotency_key": str(uuid.uuid4())}
    save_new(receipt, intent)
    response = run_cli(["asset", "create", "--file", str(path),
                        "--idempotency-key", intent["idempotency_key"]], timeout=900)
    asset_id = (response.get("data") or {}).get("asset_id")
    if not asset_id:
        raise ValueError("CLI 未返回 asset_id；先查询远端资产，不要再次上传")
    result = {"operation": "cli_oauth_asset_upload", "status": "uploaded", "asset_id": asset_id,
              "sha256": intent["sha256"], "account_email": expected_email}
    save_new(str(receipt) + ".result.json", result)
    return result


def upload_target_srt(path, text_path, preflight, expected_email, receipt, review_version, review_decision):
    auth_check(expected_email)
    approved = approved_preflight(review_version, review_decision, text_path, preflight)
    path = Path(path)
    if path.suffix.lower() != ".srt" or not path.is_file():
        raise ValueError("须提供经审定的目标语言 SRT 文件")
    report = validate_preflight(preflight)
    if report.get("text_sha256") != digest(text_path):
        raise ValueError("目标语言文案与视频预检版本不一致")
    if normalized(full_text(parse_srt(path))) != normalized(read_text(text_path)):
        raise ValueError("目标语言 SRT 与预检文案正文不一致")
    intent = {"operation": "cli_oauth_srt_asset_upload", "status": "submitted_outcome_unknown",
              "sha256": digest(path), "idempotency_key": str(uuid.uuid4()),
              "review_version_sha256": approved["version_sha256"]}
    save_new(receipt, intent)
    response = run_cli(["asset", "create", "--file", str(path),
                        "--idempotency-key", intent["idempotency_key"]], timeout=180)
    asset_id = (response.get("data") or {}).get("asset_id")
    if not asset_id:
        raise ValueError("CLI 未返回 SRT asset_id；先查远端，不要再次上传")
    result = {"operation": "cli_oauth_srt_asset_upload", "status": "uploaded", "asset_id": asset_id,
              "sha256": intent["sha256"], "account_email": expected_email,
              "review_version_sha256": approved["version_sha256"]}
    save_new(str(receipt) + ".result.json", result)
    return result


def create_draft(payload_path, preflight, asset_receipt, expected_email, receipt,
                 text_path, review_version, review_decision, paid_authorization):
    account = auth_check(expected_email)
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    validate_asset_binding(payload, preflight, asset_receipt)
    if (not payload.get("title") or len(payload.get("output_languages", [])) != 1
            or payload.get("mode") not in ("speed", "precision")
            or not isinstance(payload.get("enable_video_stretching"), bool)):
        raise ValueError("网页校对草稿须有标题、单个目标语种、模式及明确的动态时长布尔值")
    approved = approved_preflight(review_version, review_decision, text_path, preflight,
                                  payload["output_languages"][0])
    scope = create_scope("cli_oauth_proofread_create", expected_email, preflight, payload_path)
    verify_paid(paid_authorization, scope, account["billing_type"])
    intent = {"operation": "cli_oauth_proofread_create", "status": "submitted_outcome_unknown",
              "asset_id": payload["video"]["asset_id"], "request_sha256": digest(payload_path),
              "idempotency_key": str(uuid.uuid4()), "account_email": expected_email,
              "review_version_sha256": approved["version_sha256"]}
    claim_paid(paid_authorization, scope)
    save_new(receipt, intent)
    response = run_cli(["video-translate", "proofreads", "create", "-d", str(payload_path),
                        "--idempotency-key", intent["idempotency_key"]], timeout=180)
    ids = (response.get("data") or {}).get("proofread_ids") or []
    if len(ids) != 1:
        raise ValueError("CLI 未返回唯一 proofread_id；先查询远端草稿，不要再次创建")
    proofread_id = ids[0]
    result = {"operation": "cli_oauth_proofread_create", "status": "created",
              "proofread_id": proofread_id, "account_email": expected_email,
              "review_url_candidate": "https://app.heygen.com/video-translation/proofread/" + quote(proofread_id, safe=""),
              "web_editor_opened_by_reviewer": False, "final_generation_submitted": False,
              "dynamic_duration_requested": payload["enable_video_stretching"],
              "review_version_sha256": approved["version_sha256"],
              **{k: scope[k] for k in ("mode", "target_language", "clip_seconds", "clip_sha256",
                                     "text_sha256", "request_sha256")}}
    save_new(str(receipt) + ".result.json", result)
    return result


def draft_status(proofread_id, expected_email):
    auth_check(expected_email)
    response = run_cli(["video-translate", "proofreads", "get", proofread_id])
    data = response.get("data") or {}
    return {k: data.get(k) for k in ("id", "status", "output_language", "failure_message")}


def remote_srt_bytes(proofread_id):
    response = run_cli(["video-translate", "proofreads", "srt", "get", proofread_id])
    url = (response.get("data") or {}).get("srt_url")
    if not url or urlparse(url).scheme != "https":
        raise ValueError("HeyGen 未返回 HTTPS Output SRT 链接")
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "video-workflow-starter"}), timeout=90) as item:
                return item.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def update_target_srt(proofread_id, expected_email, approved_srt, asset_receipt, receipt,
                      review_version, review_decision):
    auth_check(expected_email)
    approved_srt = Path(approved_srt)
    asset = json.loads(Path(asset_receipt).read_text(encoding="utf-8"))
    version = load_review(review_version)
    approved = verify_approval(version, load_review(review_decision))
    if normalized(full_text(parse_srt(approved_srt))) != normalized(version["translation"]):
        raise ValueError("目标 SRT 与当前批准译稿不一致")
    if (asset.get("operation") != "cli_oauth_srt_asset_upload" or asset.get("status") != "uploaded"
            or asset.get("account_email", "").casefold() != expected_email.casefold()
            or asset.get("sha256") != digest(approved_srt)
            or asset.get("review_version_sha256") != approved["version_sha256"]):
        raise ValueError("目标 SRT 与当前账号的上传回执不一致")
    intent = {"operation": "cli_oauth_target_srt_update", "status": "submitted_outcome_unknown",
              "proofread_id": proofread_id, "srt_sha256": asset["sha256"], "account_email": expected_email}
    save_new(receipt, intent)
    body = json.dumps({"srt": {"type": "asset_id", "asset_id": asset["asset_id"]}})
    run_cli(["video-translate", "proofreads", "srt", "update", proofread_id, "-d", body])
    remote = remote_srt_bytes(proofread_id)
    exact = remote == approved_srt.read_bytes()
    result = {"operation": "cli_oauth_target_srt_update", "status": "verified" if exact else "needs_review",
              "proofread_id": proofread_id, "approved_srt_sha256": intent["srt_sha256"],
              "roundtrip_exact": exact, "account_email": expected_email}
    save_new(str(receipt) + ".result.json", result)
    return result


def download_srt(proofread_id, expected_email, output):
    auth_check(expected_email)
    output = Path(output)
    data = remote_srt_bytes(proofread_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as f:
        f.write(data)
    receipt = {"operation": "cli_oauth_proofread_srt", "proofread_id": proofread_id,
               "account_email": expected_email, "file": str(output), "sha256": digest(output)}
    save_new(str(output) + ".receipt.json", receipt)
    return receipt


def reviewed_text_binding(approved_srt, review_version, review_decision, draft_receipt, proofread_id, expected_email):
    version = load_review(review_version)
    approved = verify_approval(version, load_review(review_decision))
    draft = json.loads(Path(draft_receipt).read_text(encoding="utf-8"))
    if (draft.get("status") != "created" or draft.get("proofread_id") != proofread_id
            or str(draft.get("account_email", "")).casefold() != expected_email.casefold()
            or str(draft.get("target_language", "")).casefold() != str(version.get("target_language", "")).casefold()):
        raise ValueError("网页草稿与当前任务、语种或账号不一致")
    if normalized(full_text(parse_srt(approved_srt))) != normalized(version["translation"]):
        raise ValueError("网页 Output SRT 正文已偏离当前获批译稿；须先返修译审并重新批准")
    # Creation is historical. A newly approved web edit may use the same draft;
    # bind the current approval to that original draft without rewriting it.
    return {**approved, "draft_receipt_sha256": digest(draft_receipt),
            "draft_review_version_sha256": draft.get("review_version_sha256")}


def prepare_web_review(proofread_id, expected_email, approved_srt, output,
                       review_version, review_decision, draft_receipt):
    auth_check(expected_email)
    approved_srt = Path(approved_srt)
    approved = reviewed_text_binding(approved_srt, review_version, review_decision,
                                     draft_receipt, proofread_id, expected_email)
    if not approved_srt.is_file() or remote_srt_bytes(proofread_id) != approved_srt.read_bytes():
        raise ValueError("当前网页 Output SRT 与本地审核稿不一致")
    template = {"proofread_id": proofread_id, "account_email": expected_email,
                "srt_sha256": digest(approved_srt), "review_version_sha256": approved["version_sha256"],
                "draft_receipt_sha256": approved["draft_receipt_sha256"],
                "web_editor_opened": False,
                "audio_listened": False, "reviewer": None, "reviewed_at": None, "decision": "pending",
                "note": "由实际审核人打开网页、逐段试听并明确确认；Agent 可如实记录回复及来源，不得自行推断通过"}
    save_new(output, template)
    return template


def generate_reviewed(proofread_id, expected_email, approved_srt, receipt, web_review_receipt,
                      draft_receipt, paid_authorization, review_version, review_decision):
    account = auth_check(expected_email)
    approved_srt = Path(approved_srt)
    if approved_srt.suffix.lower() != ".srt" or not approved_srt.is_file():
        raise ValueError("须提供网页审核后批准的 Output SRT")
    approved = reviewed_text_binding(approved_srt, review_version, review_decision,
                                     draft_receipt, proofread_id, expected_email)
    review = json.loads(Path(web_review_receipt).read_text(encoding="utf-8"))
    try:
        reviewed_time = datetime.fromisoformat(str(review.get("reviewed_at")))
        if reviewed_time.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise ValueError("网页审核时间须为带时区的 ISO 日期") from exc
    if (review.get("proofread_id") != proofread_id or
            str(review.get("account_email", "")).casefold() != expected_email.casefold() or
            review.get("decision") != "approve" or review.get("web_editor_opened") is not True or
            review.get("audio_listened") is not True or not review.get("reviewer") or
            review.get("srt_sha256") != digest(approved_srt) or
            review.get("review_version_sha256") != approved["version_sha256"]):
        raise ValueError("缺同账号、同任务、同 SRT 的网页试听与人工批准记录")
    if (review.get("draft_receipt_sha256") != approved["draft_receipt_sha256"]
            and ("draft_receipt_sha256" in review
                 or approved["draft_review_version_sha256"] != approved["version_sha256"])):
        raise ValueError("网页修订审核未绑定当前草稿；请重新准备审核记录")
    scope = generate_scope("cli_oauth_proofread_generate", expected_email, draft_receipt,
                           approved_srt, proofread_id)
    verify_paid(paid_authorization, scope, account["billing_type"])
    remote = remote_srt_bytes(proofread_id)
    if approved_srt.read_bytes() != remote:
        raise ValueError("HeyGen 当前 Output SRT 与已批准文件不同；请重新下载、审核")
    intent = {"operation": "cli_oauth_proofread_generate", "status": "submitted_outcome_unknown",
              "proofread_id": proofread_id, "srt_sha256": digest(approved_srt),
              "idempotency_key": str(uuid.uuid4()), "account_email": expected_email}
    claim_paid(paid_authorization, scope)
    save_new(receipt, intent)
    response = run_cli(["video-translate", "proofreads", "generate", proofread_id,
                        "--idempotency-key", intent["idempotency_key"]], timeout=180)
    data = response.get("data") or {}
    if not data.get("video_translation_id"):
        raise ValueError("CLI 未返回最终任务 ID；先查远端，不要再次生成")
    result = {"operation": "cli_oauth_proofread_generate", "status": "submitted",
              "proofread_id": proofread_id, "video_translation_id": data["video_translation_id"],
              "srt_sha256": intent["srt_sha256"], "account_email": expected_email,
              "review_version_sha256": approved["version_sha256"],
              "draft_receipt_sha256": approved["draft_receipt_sha256"],
              "draft_review_version_sha256": approved["draft_review_version_sha256"]}
    save_new(str(receipt) + ".result.json", result)
    return result


def video_status(job_id, expected_email):
    auth_check(expected_email)
    data = (run_cli(["video-translate", "get", job_id]).get("data") or {})
    return {k: data.get(k) for k in ("id", "status", "output_language", "failure_message")}


def download_video(job_id, expected_email, output):
    auth_check(expected_email)
    data = (run_cli(["video-translate", "get", job_id]).get("data") or {})
    url = data.get("video_url")
    if data.get("status") != "completed" or not url or urlparse(url).scheme != "https":
        raise ValueError("任务未完成或没有可下载的 HTTPS 成片")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    if output.exists() or temporary.exists():
        raise FileExistsError("目标或未完成下载文件已存在；不会覆盖")
    try:
        with urlopen(Request(url, headers={"User-Agent": "video-workflow-starter"}), timeout=120) as item:
            with temporary.open("xb") as f:
                shutil.copyfileobj(item, f, 1024 * 1024)
        if temporary.stat().st_size == 0:
            raise ValueError("下载文件为空")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    result = {"operation": "cli_oauth_download", "status": "downloaded", "job_id": job_id,
              "file": str(output), "sha256": digest(output), "bytes": output.stat().st_size,
              "account_email": expected_email}
    save_new(str(output) + ".receipt.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    a = sub.add_parser("auth-check"); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("upload-asset"); a.add_argument("--file", required=True); a.add_argument("--preflight", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--receipt", required=True)
    a = sub.add_parser("upload-target-srt"); a.add_argument("--file", required=True); a.add_argument("--text", required=True); a.add_argument("--preflight", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--receipt", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True)
    a = sub.add_parser("create-draft"); a.add_argument("--payload", required=True); a.add_argument("--preflight", required=True); a.add_argument("--asset-receipt", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--receipt", required=True); a.add_argument("--text", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--paid-authorization", required=True); a.add_argument("--confirm-paid", action="store_true")
    a = sub.add_parser("draft-status"); a.add_argument("--proofread-id", required=True); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("download-srt"); a.add_argument("--proofread-id", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("prepare-web-review"); a.add_argument("--proofread-id", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--approved-srt", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--draft-receipt", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("update-target-srt"); a.add_argument("--proofread-id", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--approved-srt", required=True); a.add_argument("--asset-receipt", required=True); a.add_argument("--receipt", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True)
    a = sub.add_parser("generate-reviewed"); a.add_argument("--proofread-id", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--approved-srt", required=True); a.add_argument("--web-review-receipt", required=True); a.add_argument("--draft-receipt", required=True); a.add_argument("--review-version", required=True); a.add_argument("--review-decision", required=True); a.add_argument("--paid-authorization", required=True); a.add_argument("--receipt", required=True); a.add_argument("--confirm-paid", action="store_true")
    a = sub.add_parser("video-status"); a.add_argument("--job-id", required=True); a.add_argument("--expected-email", required=True)
    a = sub.add_parser("download-video"); a.add_argument("--job-id", required=True); a.add_argument("--expected-email", required=True); a.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.action == "auth-check": result = auth_check(args.expected_email)
        elif args.action == "upload-asset": result = upload_asset(args.file, args.preflight, args.expected_email, args.receipt)
        elif args.action == "upload-target-srt": result = upload_target_srt(args.file, args.text, args.preflight, args.expected_email, args.receipt, args.review_version, args.review_decision)
        elif args.action == "create-draft":
            if not args.confirm_paid: raise ValueError("创建 Proofread 草稿可能消耗额度；须针对该任务授权并传 --confirm-paid")
            result = create_draft(args.payload, args.preflight, args.asset_receipt, args.expected_email, args.receipt,
                                  args.text, args.review_version, args.review_decision, args.paid_authorization)
        elif args.action == "draft-status": result = draft_status(args.proofread_id, args.expected_email)
        elif args.action == "download-srt": result = download_srt(args.proofread_id, args.expected_email, args.out)
        elif args.action == "prepare-web-review": result = prepare_web_review(args.proofread_id, args.expected_email, args.approved_srt, args.out, args.review_version, args.review_decision, args.draft_receipt)
        elif args.action == "update-target-srt": result = update_target_srt(args.proofread_id, args.expected_email, args.approved_srt, args.asset_receipt, args.receipt, args.review_version, args.review_decision)
        elif args.action == "generate-reviewed":
            if not args.confirm_paid: raise ValueError("最终生成须针对已审核任务授权并传 --confirm-paid")
            result = generate_reviewed(args.proofread_id, args.expected_email, args.approved_srt, args.receipt,
                                       args.web_review_receipt, args.draft_receipt, args.paid_authorization,
                                       args.review_version, args.review_decision)
        elif args.action == "video-status": result = video_status(args.job_id, args.expected_email)
        else: result = download_video(args.job_id, args.expected_email, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # CLI/provider errors and signed URLs can contain private data: print only safe local errors.
        message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else "请核对本地意图回执与远端状态；结果未知时不要重复提交"
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "message": message}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
