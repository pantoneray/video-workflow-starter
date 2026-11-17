"""Deterministic review continuation; uses existing publication/translation scripts.

This callback only creates review artifacts. No HeyGen, YouTube, new scheduler,
or production state writer. The caller owns current round and model permission.
"""
import json
from pathlib import Path

from publication_assets import draft
from review_html import render
from review_protocol import validate_receipt, validate_round
from review_receipts import encode, immutable, segment
from translation_review import human_decision, load, model_stage, version_digest


def verify_displayed_translation(content, language):
    """Bind the evidence actually shown to the immutable approved version."""
    version = content["translation_version"]
    if version.get("target_language") != language:
        raise ValueError("translation language differs from review round")
    pairs = (("translation", "translation"),
             ("backtranslation", "blind_backtranslation"),
             ("independent_translation", "independent_translation"),
             ("differences", "independent_review"))
    for shown, stored in pairs:
        value = version.get(stored)
        if not isinstance(value, str) or not value.strip() or content.get(shown) != value:
            raise ValueError("displayed evidence differs from version: " + shown)
    if content.get("original") != version.get("source", {}).get("original_exact"):
        raise ValueError("displayed source differs from translation source")
    for key in ("backtranslation_provider", "independent_provider"):
        if not isinstance(content.get(key), str) or not content[key].strip():
            raise ValueError("actual evidence provider missing: " + key)
    return version


def continuation(round_path, output, *, model=None, provider=None, allow_model=False):
    output = Path(output)

    def advance(receipt, routed):
        current = load(round_path)
        verified = validate_receipt(current, receipt, entry=current["entry"])
        if verified != routed:
            raise ValueError("routing mismatch")
        root = output / routed["receipt_id"]
        root.mkdir(parents=True, exist_ok=True)
        results, errors = [], []
        for item, decision in ((i, next(d for d in receipt["items"] if d["id"] == i["id"])) for i in current["items"]):
            folder = root / segment(item["id"])
            folder.mkdir(exist_ok=True)
            try:
                if decision["decision"] == "pending":
                    result = {"id": item["id"], "state": "waiting", "next_round_required": True}
                elif decision["decision"] == "needs_changes":
                    result = {"id": item["id"], "state": "awaiting_revision", "base_version": item["version"],
                              "base_sha256": version_digest(item), "feedback": decision["comment"],
                              "next_version_required": True, "previous_approval_reusable": False}
                    immutable(folder / "revision-request.json", encode(result))
                elif current["stage"] == "T1":
                    content = item["content"]
                    choice = decision["selected_text"]
                    selected = {"id": item["id"], "version": item["version"],
                                "receipt_id": routed["receipt_id"], "selected_text": choice,
                                "production_text": content[choice], "original_A": content["A"],
                                "source": content.get("source"), "mapping": content.get("mapping"),
                                "reviewed_content_sha256": version_digest(item),
                                "hook_mode": content.get("hook_mode", "none") if choice == "B" else "none",
                                "translation_approval_reusable": False,
                                "external_actions_authorized": False}
                    immutable(folder / "selected-copy.json", encode(selected))
                    result = {"id": item["id"], "state": "awaiting_translation_and_independent_review",
                              "selected_copy": str(folder / "selected-copy.json"),
                              "external_actions_authorized": False}
                elif current["stage"] == "T2":
                    version = verify_displayed_translation(item["content"], current["language"])
                    approval = human_decision(version, "local_review_receipt", "approve",
                                              decision["comment"] or "Explicit approval with required checks completed")
                    approval["at"] = receipt["submitted_at"]
                    approval["receipt_id"] = routed["receipt_id"]
                    immutable(folder / "translation-approval.json", encode(approval))
                    candidate_path = folder / "metadata-candidate.json"
                    if candidate_path.exists():
                        candidate = load(candidate_path)
                        if candidate["version_sha256"] != version_digest(version):
                            raise ValueError("candidate version conflict")
                    else:
                        if not allow_model or not model:
                            raise ValueError("metadata model permission/configuration missing")
                        def cached_provider(prompt, selected_model):
                            return model_stage("metadata", prompt, selected_model, folder / "model", provider=provider)
                        candidate = draft(version, approval, model, cached_provider)
                        immutable(candidate_path, encode(candidate))
                    next_round = {**{k: current[k] for k in ("schema_version", "task_id", "language", "batch", "entry")},
                                  "stage": "T3", "version": "v1", "round_id": current["round_id"] + "-T3-" + item["id"],
                                  "items": [{"id": item["id"], "version": "v1", "content": candidate,
                                             "required_checks": ["正文回应标题和封面文字", "目标语自然易懂", "无夸大或歪曲", "编号与素材对应"],
                                             "approval_blockers": []}]}
                    validate_round(next_round)
                    immutable(folder / "T3-v1.json", encode(next_round))
                    immutable(folder / "T3-v1.html", render(next_round))
                    result = {"id": item["id"], "state": "next_review_ready", "round": str(folder / "T3-v1.json"),
                              "page": str(folder / "T3-v1.html"), "cover_image_approved": False}
                else:
                    result = {"id": item["id"], "state": "approved_for_stage_only", "stage": current["stage"],
                              "external_actions_authorized": False}
                immutable(folder / "result.json", encode(result))
                results.append(result)
            except Exception as exc:
                errors.append({"id": item["id"], "error": type(exc).__name__})
        if errors:
            # Preserve successes; retry uses the same paths/model result cache.
            raise RuntimeError("review continuation incomplete: " + json.dumps(errors))
        return {"items": results, "external_actions_authorized": False}

    return advance
