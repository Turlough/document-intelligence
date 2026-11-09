from __future__ import annotations

from PyQt6.QtCore import QRectF

QWEN_BBOX_SCALE = 999.0


def qwen_bbox_to_rectf(bbox: list[int], width: int, height: int) -> QRectF:
    x1, y1, x2, y2 = bbox
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1
    left = x1 / QWEN_BBOX_SCALE * width
    top = y1 / QWEN_BBOX_SCALE * height
    w = max(1.0, (x2 - x1) / QWEN_BBOX_SCALE * width)
    h = max(1.0, (y2 - y1) / QWEN_BBOX_SCALE * height)
    return QRectF(left, top, w, h)
