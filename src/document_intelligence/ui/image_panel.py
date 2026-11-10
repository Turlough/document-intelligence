from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
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
_TOOLBAR_BTN_HEIGHT = 22
_VIEWER_BACKGROUND = QColor(0xE8, 0xE8, 0xE8)


def _compact_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.setMaximumHeight(_TOOLBAR_BTN_HEIGHT)
    font = QFont(btn.font())
    if font.pointSize() > 0:
        font.setPointSize(max(8, font.pointSize() - 1))
    else:
        font.setPixelSize(max(11, font.pixelSize() - 2))
    btn.setFont(font)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return btn


class ImagePanel(QWidget):
    """Document viewer with page navigation and zoom controls."""

    page_index_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(True)
        panel_bg = self.palette()
        panel_bg.setColor(self.backgroundRole(), _VIEWER_BACKGROUND)
        self.setPalette(panel_bg)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._path: Path | None = None
        self._page_count = 1
        self._page_index = 0
        self._image_width = 1
        self._image_height = 1
        self._highlight_items: list[QGraphicsRectItem] = []
        self._needs_initial_fit = False

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(_VIEWER_BACKGROUND))
        self._view = QGraphicsView(self._scene)
        self._view.setBackgroundBrush(QBrush(_VIEWER_BACKGROUND))
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self._btn_first = _compact_button("First")
        self._btn_prev = _compact_button("Previous")
        self._btn_next = _compact_button("Next")
        self._btn_last = _compact_button("Last")
        self._btn_zoom_in = _compact_button("+")
        self._btn_zoom_out = _compact_button("−")
        self._btn_auto = _compact_button("auto")
        self._btn_fit_width = _compact_button("width")
        self._btn_fit_height = _compact_button("height")

        page_group = QGroupBox("Page")
        page_group.setFlat(True)
        page_row = QHBoxLayout(page_group)
        page_row.setContentsMargins(6, 2, 6, 4)
        page_row.setSpacing(4)
        page_row.addWidget(self._btn_first)
        page_row.addWidget(self._btn_prev)
        page_row.addWidget(self._btn_next)
        page_row.addWidget(self._btn_last)
        page_row.addSpacing(8)
        self._page_label = QLabel("—")
        page_row.addWidget(self._page_label)

        zoom_group = QGroupBox("Zoom")
        zoom_group.setFlat(True)
        zoom_row = QHBoxLayout(zoom_group)
        zoom_row.setContentsMargins(6, 2, 6, 4)
        zoom_row.setSpacing(4)
        zoom_row.addWidget(self._btn_zoom_in)
        zoom_row.addWidget(self._btn_zoom_out)
        zoom_row.addWidget(self._btn_auto)
        zoom_row.addWidget(self._btn_fit_width)
        zoom_row.addWidget(self._btn_fit_height)

        self._toolbar = QWidget()
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 0)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(page_group)
        toolbar_layout.addWidget(zoom_group)
        toolbar_layout.addStretch()

        self._canvas = QWidget()
        self._canvas.setAutoFillBackground(True)
        canvas_bg = self._canvas.palette()
        canvas_bg.setColor(self._canvas.backgroundRole(), _VIEWER_BACKGROUND)
        self._canvas.setPalette(canvas_bg)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        canvas_layout = QVBoxLayout(self._canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self._view)

        self._page_progress = QProgressBar()
        self._page_progress.setRange(0, 1)
        self._page_progress.setValue(0)
        self._page_progress.setTextVisible(True)
        self._page_progress.setFormat("Page %v of %m")
        self._page_progress.setVisible(False)
        self._page_progress.setMaximumHeight(20)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)
        layout.addWidget(self._page_progress)

        self._btn_first.clicked.connect(lambda: self._go_to_page(0))
        self._btn_prev.clicked.connect(lambda: self._go_to_page(self._page_index - 1))
        self._btn_next.clicked.connect(lambda: self._go_to_page(self._page_index + 1))
        self._btn_last.clicked.connect(
            lambda: self._go_to_page(max(0, self._page_count - 1))
        )
        self._btn_zoom_in.clicked.connect(self._zoom_in)
        self._btn_zoom_out.clicked.connect(self._zoom_out)
        self._btn_auto.clicked.connect(self._fit_view)
        self._btn_fit_width.clicked.connect(self._fit_width)
        self._btn_fit_height.clicked.connect(self._fit_height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._needs_initial_fit:
            self._schedule_fit()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._needs_initial_fit:
            self._schedule_fit()

    def _schedule_fit(self) -> None:
        QTimer.singleShot(0, self._fit_view_if_ready)

    def _fit_view_if_ready(self) -> None:
        if not self._needs_initial_fit:
            return
        if self._view.viewport().width() < 2 or self._view.viewport().height() < 2:
            return
        self._fit_view()
        self._needs_initial_fit = False

    def page_index(self) -> int:
        return self._page_index

    def document_path(self) -> Path | None:
        return self._path

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
        if label_bbox:
            self._add_highlight_rect(label_bbox, _LABEL_PEN)
        if value_bbox:
            self._add_highlight_rect(value_bbox, _VALUE_PEN)

    def _add_highlight_rect(self, bbox: list[int], pen: QPen) -> QRectF:
        rect = qwen_bbox_to_rectf(bbox, self._image_width, self._image_height)
        item = QGraphicsRectItem(rect)
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setZValue(self._pixmap_item.zValue() + 1)
        self._scene.addItem(item)
        self._highlight_items.append(item)
        return rect

    def show_path(self, path: Path | None) -> None:
        if path is None:
            self._path = None
            self._set_image(placeholder_image("No file selected"))
            self._update_nav_buttons()
            self._needs_initial_fit = True
            self._schedule_fit()
            return
        self.show_page(path, 0)

    def show_page(self, path: Path, page_index: int, *, refit: bool = True) -> None:
        prev_index = self._page_index
        self._path = path
        self._page_count = document_page_count(path)
        self._page_index = max(0, min(page_index, max(0, self._page_count - 1)))
        try:
            image = load_document_page(path, self._page_index)
        except (OSError, IndexError):
            image = placeholder_image(f"Could not load\n{path.name}")
        if image is None:
            image = placeholder_image(f"Not found\n{path.name}")
        self._set_image(image)
        self._update_nav_buttons()
        if refit:
            self._needs_initial_fit = True
            self._schedule_fit()
        self._update_page_label()
        if prev_index != self._page_index:
            self.page_index_changed.emit(self._page_index)

    def _go_to_page(self, page_index: int) -> None:
        if self._path is None:
            return
        self.show_page(self._path, page_index)

    def _update_page_label(self) -> None:
        if self._path is None:
            self._page_label.setText("—")
        else:
            self._page_label.setText(
                f"{self._page_index + 1} / {self._page_count}"
            )

    def _update_nav_buttons(self) -> None:
        at_start = self._page_index <= 0
        at_end = self._page_index >= self._page_count - 1
        no_doc = self._path is None
        self._btn_first.setEnabled(not no_doc and not at_start)
        self._btn_prev.setEnabled(not no_doc and not at_start)
        self._btn_next.setEnabled(not no_doc and not at_end)
        self._btn_last.setEnabled(not no_doc and not at_end)
        self._update_page_label()

    def _set_image(self, image: Image.Image) -> None:
        self.clear_highlights()
        self._image_width, self._image_height = image.size
        qimage = pil_to_qimage(image)
        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())

    def _zoom_in(self) -> None:
        self._needs_initial_fit = False
        self._view.scale(1.2, 1.2)

    def _zoom_out(self) -> None:
        self._needs_initial_fit = False
        self._view.scale(1 / 1.2, 1 / 1.2)

    def _image_rect(self) -> QRectF:
        return self._pixmap_item.boundingRect().normalized()

    def _viewport_size(self) -> tuple[int, int]:
        vp = self._view.viewport()
        return vp.width(), vp.height()

    def _apply_viewport_fit(self, mode: str) -> None:
        """Fit the page in the viewport: auto | width | height."""
        self._needs_initial_fit = False
        rect = self._image_rect()
        if rect.width() < 1 or rect.height() < 1:
            return
        vp_w, vp_h = self._viewport_size()
        if vp_w < 2 or vp_h < 2:
            return

        saved_anchor = self._view.transformationAnchor()
        self._view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self._view.resetTransform()
        try:
            if mode == "auto":
                self._view.fitInView(
                    rect,
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
            elif mode == "width":
                scale = vp_w / rect.width()
                self._view.setTransform(QTransform.fromScale(scale, scale))
                self._view.centerOn(rect.center())
            elif mode == "height":
                scale = vp_h / rect.height()
                self._view.setTransform(QTransform.fromScale(scale, scale))
                self._view.centerOn(rect.center())
        finally:
            self._view.setTransformationAnchor(saved_anchor)

    def _fit_view(self) -> None:
        self._apply_viewport_fit("auto")

    def _fit_width(self) -> None:
        self._apply_viewport_fit("width")

    def _fit_height(self) -> None:
        self._apply_viewport_fit("height")
