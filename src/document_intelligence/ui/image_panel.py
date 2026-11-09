from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services.bbox import qwen_bbox_to_rectf
from ..services.image_loader import (
    document_page_count,
    load_document_page,
    pil_to_qimage,
    placeholder_image,
)

_LABEL_PEN = QPen(QColor(0, 170, 0), 2, Qt.PenStyle.DashLine)
_VALUE_PEN = QPen(QColor(0, 170, 0), 2, Qt.PenStyle.SolidLine)
_FIELD_FIT_MARGIN = 0.12


class ImagePanel(QWidget):
    """Top-right image viewer with basic zoom and fit controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page_count = 1
        self._page_index = 0
        self._image_width = 1
        self._image_height = 1
        self._highlight_items: list[QGraphicsRectItem] = []

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self._page_label = QLabel("Page 1 of 1")
        self._btn_zoom_in = QPushButton("Zoom +")
        self._btn_zoom_out = QPushButton("Zoom −")
        self._btn_fit = QPushButton("Fit")

        nav = QHBoxLayout()
        nav.addWidget(self._btn_zoom_in)
        nav.addWidget(self._btn_zoom_out)
        nav.addWidget(self._btn_fit)
        nav.addStretch()
        nav.addWidget(self._page_label)

        self._page_progress = QProgressBar()
        self._page_progress.setRange(0, 1)
        self._page_progress.setValue(0)
        self._page_progress.setTextVisible(True)
        self._page_progress.setFormat("Page %v of %m")
        self._page_progress.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view, stretch=1)
        layout.addLayout(nav)
        layout.addWidget(self._page_progress)

        self._btn_zoom_in.clicked.connect(self._zoom_in)
        self._btn_zoom_out.clicked.connect(self._zoom_out)
        self._btn_fit.clicked.connect(self._fit_view)

    def set_page_progress(self, page_index: int, page_count: int) -> None:
        if page_count <= 0:
            self._page_progress.setVisible(False)
            return
        self._page_progress.setVisible(True)
        self._page_progress.setMaximum(page_count)
        self._page_progress.setValue(min(page_index + 1, page_count))

    def clear_page_progress(self) -> None:
        self._page_progress.setVisible(False)
        self._page_progress.setValue(0)

    def clear_highlights(self) -> None:
        for item in self._highlight_items:
            self._scene.removeItem(item)
        self._highlight_items.clear()

    def highlight_bboxes(
        self,
        label_bbox: list[int] | None,
        value_bbox: list[int] | None,
    ) -> None:
        self.clear_highlights()
        fit_rects: list[QRectF] = []
        if label_bbox:
            fit_rects.append(
                self._add_highlight_rect(label_bbox, _LABEL_PEN)
            )
        if value_bbox:
            fit_rects.append(
                self._add_highlight_rect(value_bbox, _VALUE_PEN)
            )
        if fit_rects:
            self._fit_rects_in_view(fit_rects)

    def _add_highlight_rect(self, bbox: list[int], pen: QPen) -> QRectF:
        rect = qwen_bbox_to_rectf(bbox, self._image_width, self._image_height)
        item = QGraphicsRectItem(rect)
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setZValue(self._pixmap_item.zValue() + 1)
        self._scene.addItem(item)
        self._highlight_items.append(item)
        return rect

    def _fit_rects_in_view(self, rects: list[QRectF]) -> None:
        if not rects:
            return
        region = QRectF(rects[0])
        for rect in rects[1:]:
            region = region.united(rect)
        if region.width() < 1.0 or region.height() < 1.0:
            return
        pad_x = max(region.width() * _FIELD_FIT_MARGIN, 8.0)
        pad_y = max(region.height() * _FIELD_FIT_MARGIN, 8.0)
        padded = region.adjusted(-pad_x, -pad_y, pad_x, pad_y)
        bounds = self._pixmap_item.boundingRect()
        padded = padded.intersected(bounds)
        if padded.width() < 1.0 or padded.height() < 1.0:
            padded = region.intersected(bounds)
        self._view.resetTransform()
        self._view.fitInView(padded, Qt.AspectRatioMode.KeepAspectRatio)

    def show_path(self, path: Path | None) -> None:
        if path is None:
            self._set_image(placeholder_image("No file selected"))
            self._page_label.setText("Page —")
            return
        self.show_page(path, 0)

    def show_page(self, path: Path, page_index: int) -> None:
        self._page_count = document_page_count(path)
        self._page_index = max(0, min(page_index, max(0, self._page_count - 1)))
        try:
            image = load_document_page(path, self._page_index)
        except (OSError, IndexError):
            image = placeholder_image(f"Could not load\n{path.name}")
        if image is None:
            image = placeholder_image(f"Not found\n{path.name}")
        self._set_image(image)
        self._page_label.setText(
            f"Page {self._page_index + 1} of {self._page_count}"
        )
        self._fit_view()

    def _set_image(self, image: Image.Image) -> None:
        self.clear_highlights()
        self._image_width, self._image_height = image.size
        qimage = pil_to_qimage(image)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

    def _zoom_in(self) -> None:
        self._view.scale(1.2, 1.2)

    def _zoom_out(self) -> None:
        self._view.scale(1 / 1.2, 1 / 1.2)

    def _fit_view(self) -> None:
        self._view.resetTransform()
        self._view.fitInView(
            self._pixmap_item,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
