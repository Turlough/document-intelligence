from __future__ import annotations

import json
import re
from pathlib import Path


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

DEFAULT_EXTRACTION_PROMPT = (
    "Read this document image. Extract all visible labeled fields as a JSON object "
    "whose keys are field labels and values are strings. Reply with JSON only, "
    "no markdown or commentary."
)


def extraction_prompt_for_page(
    page_index: int,
    page_count: int,
    base: str = DEFAULT_EXTRACTION_PROMPT,
) -> str:
    if page_count <= 1:
        return base
    page_no = page_index + 1
    return (
        f"This is page {page_no} of {page_count} of the same document. "
        f"{base}"
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


def merge_extracted_fields(page_maps: list[dict[str, str]]) -> dict[str, str]:
    """Merge per-page field maps; first non-empty value wins for duplicate keys."""
    merged: dict[str, str] = {}
    for fields in page_maps:
        for key, value in fields.items():
            text = value.strip()
            if not text:
                continue
            existing = merged.get(key, "").strip()
            if not existing:
                merged[key] = value
    return merged


def extraction_json_path(source: Path) -> Path:
    return source.parent / f"{source.stem}.json"


def write_extraction_json(source: Path, fields: dict[str, str]) -> Path:
    out = extraction_json_path(source)
    out.write_text(
        json.dumps(fields, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def value_for_field(fields: dict[str, str], field_name: str) -> str:
    if field_name in fields:
        return fields[field_name]
    lowered = field_name.casefold()
    for key, value in fields.items():
        if key.casefold() == lowered:
            return value
    return ""
