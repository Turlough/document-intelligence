from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..models.field_extraction import FieldExtraction

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

DEFAULT_EXTRACTION_PROMPT = (
    "Read this document image. Extract every visible labeled form field. "
    "Reply with JSON only — no markdown. Use this shape:\n"
    '{"fields": [{"name": "<label text>", "value": "<value text>", '
    '"label_bbox": [x1, y1, x2, y2], "value_bbox": [x1, y1, x2, y2]}]}\n'
    "Coordinates are Qwen-style integers from 0 to 999 (relative to image width and height). "
    "Use null for a missing box when text is inferred but not visible."
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


def _fields_from_array(items: list[Any]) -> list[FieldExtraction]:
    out: list[FieldExtraction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fe = FieldExtraction.from_dict(item)
        if not fe.name and fe.value:
            fe.name = fe.value
        if fe.name or fe.value:
            out.append(fe)
    return out


def _fields_from_flat_dict(data: dict[str, Any]) -> list[FieldExtraction]:
    out: list[FieldExtraction] = []
    for key, value in data.items():
        if isinstance(value, dict):
            nested = FieldExtraction.from_dict({"name": key, **value})
            if nested.value == "" and "value" not in value:
                text = value.get("text") or value.get("content")
                if text is not None:
                    nested.value = str(text)
            out.append(nested)
        elif isinstance(value, list):
            out.append(
                FieldExtraction(
                    name=str(key),
                    value=json.dumps(value, ensure_ascii=False),
                )
            )
        else:
            out.append(
                FieldExtraction(name=str(key), value="" if value is None else str(value))
            )
    return out


def parse_page_extractions(text: str) -> tuple[list[FieldExtraction], str | None]:
    """Parse a model page response into structured fields, or raw fallback text."""
    cleaned = strip_json_fences(text)
    if not cleaned:
        return [], None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return [], text

    if isinstance(data, list):
        fields = _fields_from_array(data)
        return fields, None if fields else text

    if not isinstance(data, dict):
        return [
            FieldExtraction(name="value", value="" if data is None else str(data))
        ], None

    if "fields" in data and isinstance(data["fields"], list):
        fields = _fields_from_array(data["fields"])
        if fields:
            return fields, None

    skip = {"fields", "pages", "page"}
    flat = {k: v for k, v in data.items() if k not in skip}
    if flat:
        fields = _fields_from_flat_dict(flat)
        if fields:
            return fields, None

    return [], text


def parse_model_object(text: str) -> dict[str, str] | None:
    """Flat string map for legacy callers."""
    fields, raw = parse_page_extractions(text)
    if raw is not None:
        return None
    if not fields:
        return {}
    return extractions_to_flat(fields)


def extractions_to_flat(fields: list[FieldExtraction]) -> dict[str, str]:
    out: dict[str, str] = {}
    for fe in fields:
        out[fe.name] = fe.value
    return out


def merge_extracted_fields(
    page_extractions: list[list[FieldExtraction]],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for fields in page_extractions:
        for fe in fields:
            text = fe.value.strip()
            if not text:
                continue
            existing = merged.get(fe.name, "").strip()
            if not existing:
                merged[fe.name] = fe.value
    return merged


def extraction_json_path(source: Path) -> Path:
    return source.parent / f"{source.stem}.json"


def load_extraction_json(source: Path) -> list[list[FieldExtraction]] | None:
    """Load `{stem}.json` beside the document, if present."""
    path = extraction_json_path(source)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load extraction JSON %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    pages_raw = data.get("pages")
    if not isinstance(pages_raw, list):
        return None
    pages: list[list[FieldExtraction]] = []
    for page in pages_raw:
        if isinstance(page, dict) and isinstance(page.get("fields"), list):
            fields = _fields_from_array(page["fields"])
        elif isinstance(page, dict):
            fields = _fields_from_flat_dict(page)
        elif isinstance(page, list):
            fields = _fields_from_array(page)
        else:
            fields = []
        pages.append(fields)
    return pages


def write_extraction_json(
    source: Path, page_extractions: list[list[FieldExtraction]]
) -> Path:
    out = extraction_json_path(source)
    payload = {
        "pages": [
            {"fields": [fe.to_dict() for fe in page_fields]}
            for page_fields in page_extractions
        ]
    }
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
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


def value_for_extraction(
    extractions: list[FieldExtraction], field_name: str
) -> str:
    lowered = field_name.casefold()
    for fe in extractions:
        if fe.name.casefold() == lowered:
            return fe.value
    return ""


def find_field_extraction(
    page_extractions: list[list[FieldExtraction]],
    field_name: str,
    *,
    page_index: int | None = None,
) -> tuple[int, FieldExtraction] | None:
    """Locate a field on a page; prefers a page with boxes when page is unspecified."""
    lowered = field_name.casefold()

    def match_on_page(page_idx: int) -> FieldExtraction | None:
        for fe in page_extractions[page_idx]:
            if fe.name.casefold() == lowered:
                return fe
        return None

    if page_index is not None:
        if page_index < 0 or page_index >= len(page_extractions):
            return None
        hit = match_on_page(page_index)
        return (page_index, hit) if hit else None

    with_boxes: tuple[int, FieldExtraction] | None = None
    first: tuple[int, FieldExtraction] | None = None
    for page_idx, page in enumerate(page_extractions):
        for fe in page:
            if fe.name.casefold() != lowered:
                continue
            if first is None:
                first = (page_idx, fe)
            if fe.label_bbox or fe.value_bbox:
                with_boxes = (page_idx, fe)
                break
        if with_boxes:
            break
    return with_boxes or first
