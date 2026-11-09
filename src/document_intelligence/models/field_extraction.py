from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FieldExtraction:
    name: str
    value: str
    label_bbox: list[int] | None = None
    value_bbox: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "label_bbox": self.label_bbox,
            "value_bbox": self.value_bbox,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FieldExtraction:
        name = str(
            raw.get("name") or raw.get("label") or raw.get("field") or ""
        ).strip()
        value = raw.get("value")
        if value is None:
            value = raw.get("text", "")
        return cls(
            name=name,
            value="" if value is None else str(value),
            label_bbox=_bbox_from_raw(
                raw.get("label_bbox") or raw.get("key_bbox") or raw.get("name_bbox")
            ),
            value_bbox=_bbox_from_raw(
                raw.get("value_bbox") or raw.get("text_bbox")
            ),
        )


def _bbox_from_raw(raw: object) -> list[int] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        inner = raw.get("bbox_2d") or raw.get("bbox")
        return _bbox_from_raw(inner)
    if not isinstance(raw, list) or len(raw) < 4:
        return None
    try:
        coords = [int(round(float(x))) for x in raw[:4]]
    except (TypeError, ValueError):
        return None
    return coords
