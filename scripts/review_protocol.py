"""Shared T1–T4 receipt validation. No scheduling, approval writes or network I/O.

The receiver must load the current round from its own trusted task registry, not
from the submitted receipt. Transport authentication and durable deduplication
belong to the receiver. A valid receipt never authorizes paid generation/upload.
"""
from datetime import datetime
from translation_review import version_digest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_round(current):
    require(current.get("schema_version") == 1, "unsupported schema")
    for key in ("task_id", "language", "version", "batch", "round_id"):
        require(text(current.get(key)), "missing " + key)
    require(current.get("stage") in ("T1", "T2", "T3", "T4"), "invalid stage")
    require(current.get("entry") in ("local_html", "notion"), "invalid entry")
    items = current.get("items")
    require(isinstance(items, list) and bool(items), "empty round")
    ids = set()
    for item in items:
        require(isinstance(item, dict), "invalid item")
        require(text(item.get("id")) and item["id"] not in ids, "duplicate/missing item")
        ids.add(item["id"])
        require(text(item.get("version")), "missing item version")
        require(isinstance(item.get("content"), dict) and bool(item["content"]), "missing content")
        checks = item.get("required_checks")
        require(isinstance(checks, list) and bool(checks), "required checks missing")
        require(all(text(x) for x in checks) and len(set(checks)) == len(checks), "invalid checks")
        blockers = item.get("approval_blockers")
        require(isinstance(blockers, list) and all(text(x) for x in blockers), "missing blocker evaluation")
    return version_digest(current)


def validate_receipt(current, receipt, *, entry):
    """Validate against a trusted current round; return pure per-item routing.

submitted_at is recorded but excluded from the idempotency fingerprint so a
double click cannot create a new logical decision. Changed opinions conflict
with an already accepted decision and need an explicit new review round.
"""
    binding = validate_round(current)
    require(isinstance(receipt, dict), "invalid receipt")
    for key in ("schema_version", "round_id", "task_id", "stage", "language", "version", "entry"):
        require(receipt.get(key) == current[key], "stale or mismatched " + key)
    require(entry == current["entry"], "inactive review entry")
    require(receipt.get("content_sha256") == binding, "stale content hash")
    try:
        date = datetime.fromisoformat(receipt["submitted_at"].replace("Z", "+00:00"))
        require(date.tzinfo is not None, "submission timezone required")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("invalid submission timestamp") from exc
    decisions = receipt.get("items")
    require(isinstance(decisions, list) and len(decisions) == len(current["items"]), "incomplete round")
    expected = {i["id"]: i for i in current["items"]}
    seen, routes = set(), []
    for decision in decisions:
        require(isinstance(decision, dict), "invalid decision")
        ident = decision.get("id")
        require(isinstance(ident, str) and ident in expected and ident not in seen, "unknown/duplicate item")
        seen.add(ident)
        item = expected[ident]
        require(decision.get("version") == item["version"], "stale item version")
        require(decision.get("content_sha256") == version_digest(item), "stale item hash")
        verdict = decision.get("decision")
        require(verdict in ("pending", "approved", "needs_changes"), "invalid decision")
        require(isinstance(decision.get("comment"), str), "comment must be text")
        if verdict == "needs_changes":
            require(text(decision["comment"]), "revision needs comment")
        if verdict == "approved":
            require(not item["approval_blockers"], "unresolved approval blockers")
            checks = decision.get("checks", {})
            require(isinstance(checks, dict) and all(checks.get(k) is True for k in item["required_checks"]), "required checks incomplete")
            if current["stage"] == "T1":
                require(decision.get("selected_text") in ("A", "B"), "explicit A/B selection required")
                require(text(item["content"].get(decision["selected_text"])), "selected text absent")
        next_stage = {"T1": "T2", "T2": "T3", "T3": "await_media_review", "T4": "await_upload_authorization"}[current["stage"]]
        routes.append({"id": ident, "decision": verdict, "next": next_stage if verdict == "approved" else ("revision" if verdict == "needs_changes" else "waiting")})
    logical = {"round_sha256": binding, "items": sorted(decisions, key=lambda d: d["id"])}
    return {"receipt_id": version_digest(logical), "routes": routes, "external_actions_authorized": False}
