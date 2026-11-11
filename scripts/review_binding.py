"""Bind an approved local translation to the exact HeyGen preflight text."""
import json
from pathlib import Path

from subtitle_tools import normalized, read_text
from translation_review import verify_approval
from heygen_portable import digest, validate_preflight


def approved_preflight(version_path, decision_path, text_path, preflight_path, language=None):
    version = json.loads(Path(version_path).read_text(encoding="utf-8"))
    decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
    approved = verify_approval(version, decision)
    if language and str(version.get("target_language", "")).casefold() != str(language).casefold():
        raise ValueError("人工批准的目标语种与 HeyGen 请求不一致")
    text = Path(text_path)
    if normalized(read_text(text)) != normalized(version["translation"]):
        raise ValueError("HeyGen 逐句文案与当前批准译稿不一致")
    preflight = validate_preflight(preflight_path)
    if preflight.get("text_sha256") != digest(text):
        raise ValueError("逐句文案与语速预检绑定的版本不一致")
    return {**approved, "text_sha256": digest(text), "target_language": version["target_language"]}
