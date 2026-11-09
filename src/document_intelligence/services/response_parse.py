from __future__ import annotations

import json
import re


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

DEFAULT_EXTRACTION_PROMPT = (
    "Read this document image. Extract all visible labeled fields as a JSON object "
    "whose keys are field labels and values are strings. Reply with JSON only, "
    "no markdown or commentary."
)


def strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped).strip()
    return stripped


def parse_model_object(text: str) -> dict[str, str] | None:
    """Parse assistant content into a flat string map, or None if not JSON."""
    cleaned = strip_json_fences(text)
    if not cleaned:
        return None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return {"value": "" if data is None else str(data)}
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(value, ensure_ascii=False)
        else:
            out[str(key)] = "" if value is None else str(value)
    return out


def value_for_field(fields: dict[str, str], field_name: str) -> str:
    if field_name in fields:
        return fields[field_name]
    lowered = field_name.casefold()
    for key, value in fields.items():
        if key.casefold() == lowered:
            return value
    return ""
