#!/usr/bin/env python3
"""Prepare and verify a human, task-specific HeyGen spending decision.

The receipt records an estimate and consent. It cannot cap provider billing.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_scope(operation, expected_email, preflight, payload):
    if operation not in ("cli_oauth_proofread_create", "api_key_proofread_create", "api_key_direct_translation"):
        raise ValueError("未知 HeyGen 创建操作")
    report, request = load(preflight), load(payload)
    seconds = report.get("clip_seconds")
    if (report.get("status") != "ready_for_review" or not isinstance(seconds, (int, float))
            or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0
            or not report.get("clip_sha256") or not report.get("text_sha256")):
        raise ValueError("授权前须有完整的当前视频语速预检")
    if request.get("mode") not in ("speed", "precision") or len(request.get("output_languages", [])) != 1:
        raise ValueError("授权须绑定单语种和明确的 HeyGen 模式")
    if not expected_email or "@" not in expected_email:
        raise ValueError("须填写实际 HeyGen 账号邮箱")
    return {"operation": operation, "account_email": expected_email.casefold(),
            "mode": request["mode"], "target_language": request["output_languages"][0],
            "clip_seconds": seconds, "clip_sha256": report["clip_sha256"],
            "text_sha256": report["text_sha256"], "request_sha256": sha(payload),
            "dynamic_duration_requested": request.get("enable_video_stretching", request.get("enable_dynamic_duration"))}


def generate_scope(operation, expected_email, draft_receipt, approved_srt, proofread_id):
    if operation not in ("cli_oauth_proofread_generate", "api_key_proofread_generate"):
        raise ValueError("未知 HeyGen 生成操作")
    draft = load(draft_receipt)
    if (draft.get("status") != "created" or draft.get("proofread_id") != proofread_id
            or str(draft.get("account_email", "")).casefold() != expected_email.casefold()
            or draft.get("mode") not in ("speed", "precision")
            or not draft.get("clip_sha256") or not draft.get("clip_seconds")):
        raise ValueError("生成授权需要同账号、同任务的创建结果回执")
    return {"operation": operation, "account_email": expected_email.casefold(),
            "mode": draft["mode"], "target_language": draft["target_language"],
            "clip_seconds": draft["clip_seconds"], "clip_sha256": draft["clip_sha256"],
            "text_sha256": draft["text_sha256"], "request_sha256": draft["request_sha256"],
            "dynamic_duration_requested": draft["dynamic_duration_requested"],
            "proofread_id": proofread_id, "approved_srt_sha256": sha(approved_srt)}


def prepare(scope, out):
    receipt = {**scope, "billing_type": None, "estimated_credits": None,
               "max_expected_credits": None, "pricing_source": None,
               "reviewer": None, "approved_at": None, "decision": "pending",
               "account_and_billing_confirmed": False,
               "mode_duration_and_cost_confirmed": False,
               "actual_charge_may_differ_acknowledged": False}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return receipt


def verify(path, scope, actual_billing_type):
    receipt = load(path)
    if any(receipt.get(k) != v for k, v in scope.items()):
        raise ValueError("付费授权的账号、任务、模式、时长或文件版本与当前提交不一致")
    if not actual_billing_type or receipt.get("billing_type") != actual_billing_type:
        raise ValueError("付费授权中的计费来源与当前账号不一致")
    estimate, ceiling = receipt.get("estimated_credits"), receipt.get("max_expected_credits")
    if (isinstance(estimate, bool) or isinstance(ceiling, bool)
            or not isinstance(estimate, (int, float)) or not isinstance(ceiling, (int, float))
            or not math.isfinite(estimate) or not math.isfinite(ceiling)
            or estimate <= 0 or ceiling < estimate):
        raise ValueError("须填写当前账号的正数费用估计和不低于估计的预期上限")
    try:
        approved_at = datetime.fromisoformat(str(receipt.get("approved_at")))
        if approved_at.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as exc:
        raise ValueError("付费批准时间须为带时区的 ISO 日期") from exc
    if (receipt.get("decision") != "approve" or not receipt.get("reviewer")
            or not receipt.get("pricing_source")
            or receipt.get("account_and_billing_confirmed") is not True
            or receipt.get("mode_duration_and_cost_confirmed") is not True
            or receipt.get("actual_charge_may_differ_acknowledged") is not True):
        raise ValueError("缺少实际使用者对账号、计费、模式、时长与费用的逐任务批准")
    return receipt


def claim(path, scope):
    """Consume one authorization before a potentially paid request.

    A crash or unknown remote outcome keeps the claim; investigate remotely
    instead of replaying the same permission.
    """
    marker = Path(str(path) + ".claimed.json")
    with marker.open("x", encoding="utf-8") as f:
        json.dump({"status": "claimed_outcome_unknown", "operation": scope["operation"],
                   "authorization_sha256": sha(path)}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return marker


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("prepare-create")
    a.add_argument("--operation", choices=("cli_oauth_proofread_create", "api_key_proofread_create", "api_key_direct_translation"), required=True)
    a.add_argument("--expected-email", required=True); a.add_argument("--preflight", required=True)
    a.add_argument("--payload", required=True); a.add_argument("--out", required=True)
    a = sub.add_parser("prepare-generate")
    a.add_argument("--operation", choices=("cli_oauth_proofread_generate", "api_key_proofread_generate"), required=True)
    a.add_argument("--expected-email", required=True); a.add_argument("--draft-receipt", required=True)
    a.add_argument("--approved-srt", required=True); a.add_argument("--proofread-id", required=True)
    a.add_argument("--out", required=True)
    args = p.parse_args()
    scope = (create_scope(args.operation, args.expected_email, args.preflight, args.payload)
             if args.action == "prepare-create" else
             generate_scope(args.operation, args.expected_email, args.draft_receipt, args.approved_srt, args.proofread_id))
    print(json.dumps(prepare(scope, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
