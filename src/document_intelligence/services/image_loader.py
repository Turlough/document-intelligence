from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PyQt6.QtGui import QImage

_PLACEHOLDER_SIZE = (720, 360)
_MAX_DISPLAY_PIXELS = 12_000_000


def document_page_count(path: Path) -> int:
    if not path.is_file():
        return 1
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import fitz

        doc = fitz.open(path)
        try:
            return max(1, doc.page_count)
        finally:
            doc.close()
    if suffix in {".tif", ".tiff"}:
        with Image.open(path) as probe:
            return max(1, getattr(probe, "n_frames", 1))
    return 1


def load_document_page(path: Path, page_index: int = 0) -> Image.Image | None:
    if not path.is_file():
        return None
    if page_index < 0 or page_index >= document_page_count(path):
        return None
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        image = _load_pdf_page(path, page_index)
    else:
        image = _load_raster_page(path, page_index)
    return _limit_image_size(image)


def load_first_page_image(path: Path) -> Image.Image | None:
    return load_document_page(path, 0)


def pil_to_qimage(image: Image.Image) -> QImage:
    rgb = image.convert("RGB")
    width, height = rgb.size
    bytes_per_line = 3 * width
    qimage = QImage(
        rgb.tobytes(),
        width,
        height,
        bytes_per_line,
        QImage.Format.Format_RGB888,
    )
    return qimage.copy()


def _limit_image_size(
    image: Image.Image,
    max_pixels: int = _MAX_DISPLAY_PIXELS,
) -> Image.Image:
    width, height = image.size
    if width * height <= max_pixels:
        return image
    scale = (max_pixels / (width * height)) ** 0.5
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _load_pdf_page(path: Path, page_index: int) -> Image.Image:
    import fitz

    doc = fitz.open(path)
    try:
        page = doc[page_index]
        rect = page.rect
        area = max(rect.width * rect.height, 1.0)
        zoom = min(2.0, (_MAX_DISPLAY_PIXELS / area) ** 0.5)
        zoom = max(0.75, zoom)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def _load_raster_page(path: Path, page_index: int) -> Image.Image:
    with Image.open(path) as img:
        n_frames = getattr(img, "n_frames", 1)
        if n_frames > 1:
            img.seek(page_index)
        elif page_index != 0:
            raise IndexError(f"page_index {page_index} out of range for {path.name}")
        img.load()
        if img.mode == "RGB":
            return img.copy()
        return img.convert("RGB")


def placeholder_image(message: str = "Image not found") -> Image.Image:
    from PIL import ImageDraw

    img = Image.new("RGB", _PLACEHOLDER_SIZE, color=(220, 220, 220))
    draw = ImageDraw.Draw(img)
    draw.multiline_text((20, 20), message, fill=(80, 80, 80))
    return img


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
