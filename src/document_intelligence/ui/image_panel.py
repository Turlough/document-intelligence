from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services.image_loader import (
    document_page_count,
    load_first_page_image,
    pil_to_qimage,
    placeholder_image,
)


class ImagePanel(QWidget):
    """Top-right image viewer with basic zoom and fit controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page_count = 1
        self._page_index = 0

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view, stretch=1)
        layout.addLayout(nav)

        self._btn_zoom_in.clicked.connect(self._zoom_in)
        self._btn_zoom_out.clicked.connect(self._zoom_out)
        self._btn_fit.clicked.connect(self._fit_view)

    def show_path(self, path: Path | None) -> None:
        if path is None:
            self._set_image(placeholder_image("No file selected"))
            self._page_label.setText("Page —")
            return
        try:
            image = load_first_page_image(path)
        except OSError:
            image = placeholder_image(f"Could not load\n{path.name}")
        if image is None:
            image = placeholder_image(f"Not found\n{path.name}")
        self._set_image(image)
        self._page_count = document_page_count(path)
        self._page_index = 0
        self._page_label.setText(f"Page {self._page_index + 1} of {self._page_count}")
        self._fit_view()

    def _set_image(self, image: Image.Image) -> None:
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
