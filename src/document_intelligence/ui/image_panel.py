from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
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
_FIELD_FIT_MARGIN = 0.12
_A4_HEIGHT_PER_WIDTH = 297.0 / 210.0


class _A4Viewport(QWidget):
  """Portrait A4 aspect for the image canvas."""

  def hasHeightForWidth(self) -> bool:
    return True

  def heightForWidth(self, width: int) -> int:
    return max(120, int(width * _A4_HEIGHT_PER_WIDTH))


class ImagePanel(QWidget):
  """Document viewer with page navigation and zoom controls."""

  page_index_changed = pyqtSignal(int)

  def __init__(self, parent: QWidget | None = None) -> None:
    super().__init__(parent)
    self._path: Path | None = None
    self._page_count = 1
    self._page_index = 0
    self._image_width = 1
    self._image_height = 1
    self._highlight_items: list[QGraphicsRectItem] = []

    self._scene = QGraphicsScene(self)
    self._view = QGraphicsView(self._scene)
    self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
    self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
    self._view.setTransformationAnchor(
      QGraphicsView.ViewportAnchor.AnchorUnderMouse
    )
    self._pixmap_item = QGraphicsPixmapItem()
    self._scene.addItem(self._pixmap_item)

    self._btn_first = QPushButton("First")
    self._btn_prev = QPushButton("Previous")
    self._btn_next = QPushButton("Next")
    self._btn_last = QPushButton("Last")
    self._btn_zoom_in = QPushButton("+")
    self._btn_zoom_out = QPushButton("−")
    self._btn_auto = QPushButton("auto")
    self._btn_fit_width = QPushButton("width")
    self._btn_fit_height = QPushButton("height")

    for btn in (
      self._btn_first,
      self._btn_prev,
      self._btn_next,
      self._btn_last,
      self._btn_zoom_in,
      self._btn_zoom_out,
      self._btn_auto,
      self._btn_fit_width,
      self._btn_fit_height,
    ):
      btn.setAutoDefault(False)
      btn.setDefault(False)

    nav = QHBoxLayout()
    nav.setContentsMargins(4, 4, 4, 4)
    nav.addWidget(self._btn_first)
    nav.addWidget(self._btn_prev)
    nav.addWidget(self._btn_next)
    nav.addWidget(self._btn_last)
    nav.addSpacing(12)
    nav.addWidget(self._btn_zoom_in)
    nav.addWidget(self._btn_zoom_out)
    nav.addWidget(self._btn_auto)
    nav.addWidget(self._btn_fit_width)
    nav.addWidget(self._btn_fit_height)
    nav.addStretch()

    self._a4_frame = _A4Viewport()
    self._a4_frame.setSizePolicy(
      QSizePolicy.Policy.Expanding,
      QSizePolicy.Policy.Preferred,
    )
    frame_layout = QVBoxLayout(self._a4_frame)
    frame_layout.setContentsMargins(0, 0, 0, 0)
    frame_layout.addWidget(self._view)

    self._page_progress = QProgressBar()
    self._page_progress.setRange(0, 1)
    self._page_progress.setValue(0)
    self._page_progress.setTextVisible(True)
    self._page_progress.setFormat("Page %v of %m")
    self._page_progress.setVisible(False)

    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addLayout(nav)
    layout.addWidget(self._a4_frame, stretch=1)
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

  def page_index(self) -> int:
    return self._page_index

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
      fit_rects.append(self._add_highlight_rect(label_bbox, _LABEL_PEN))
    if value_bbox:
      fit_rects.append(self._add_highlight_rect(value_bbox, _VALUE_PEN))
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
      self._path = None
      self._set_image(placeholder_image("No file selected"))
      self._update_nav_buttons()
      return
    self.show_page(path, 0)

  def show_page(self, path: Path, page_index: int) -> None:
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
    self._fit_view()
    if prev_index != self._page_index:
      self.page_index_changed.emit(self._page_index)

  def _go_to_page(self, page_index: int) -> None:
    if self._path is None:
      return
    self.show_page(self._path, page_index)

  def _update_nav_buttons(self) -> None:
    at_start = self._page_index <= 0
    at_end = self._page_index >= self._page_count - 1
    no_doc = self._path is None
    self._btn_first.setEnabled(not no_doc and not at_start)
    self._btn_prev.setEnabled(not no_doc and not at_start)
    self._btn_next.setEnabled(not no_doc and not at_end)
    self._btn_last.setEnabled(not no_doc and not at_end)

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

  def _fit_width(self) -> None:
    scene = self._pixmap_item.boundingRect()
    if scene.width() <= 0:
      return
    self._view.resetTransform()
    vp_w = self._view.viewport().width()
    self._view.scale(vp_w / scene.width(), vp_w / scene.width())

  def _fit_height(self) -> None:
    scene = self._pixmap_item.boundingRect()
    if scene.height() <= 0:
      return
    self._view.resetTransform()
    vp_h = self._view.viewport().height()
    self._view.scale(vp_h / scene.height(), vp_h / scene.height())
