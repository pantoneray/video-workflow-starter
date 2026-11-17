"""Task-level caption placement, color and source-confirmed course badge."""
import copy
import math
import re


def configure(settings, shift_up=80, highlight=None, course=None, contrast=None):
    result = copy.deepcopy(settings)
    if not math.isfinite(shift_up):
        raise ValueError("caption shift must be finite")
    y = result["captions"]["y_center"] - shift_up
    if not 1300 <= y <= 1560:
        raise ValueError("requested subtitle position exceeds supported lower safe band; review composition")
    result["captions"]["y_center"] = y
    result["layout"].setdefault("caption", {})["y_center"] = y
    if highlight:
        color = {"yellow": "#FFE14D", "green": "#8BE28B"}.get(highlight, highlight)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("highlight must be yellow, green or #RRGGBB")
        if "highlight" not in result["captions"]:
            raise ValueError("this template has no emphasis color; choose a highlight template")
        result["captions"]["highlight"] = color.upper()
    if contrast not in (None, "outline", "box"):
        raise ValueError("contrast must be outline or box")
    if contrast == "outline":
        result["captions"]["outline"] = max(4, result["captions"].get("outline", 0))
    elif contrast == "box":
        result["captions"].update(box=True, box_color="#111111")
    if course:
        if course.get("confirmed") is not True or not str(course.get("source", "")).strip():
            raise ValueError("course badge requires explicit choice and verified textual source")
        label = course.get("text", "")
        if not isinstance(label, str) or not label.strip() or len(label) > 36 or any(c in label for c in "{}\\\r\n"):
            raise ValueError("invalid or overly long course label")
        result["course_badge"] = {"text": label, "source": course["source"], "confirmed": True}
    else:
        result.pop("course_badge", None)
    return result
