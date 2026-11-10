from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models.field_extraction import FieldExtraction, vertical_sort_key
from ..models.project_config import ProjectConfig
from ..services.config_loader import (
    config_directory,
    discover_project_configs,
    load_project_config,
)
from ..services.response_parse import (
    find_field_extraction,
    load_extraction_json,
    merge_extracted_fields,
)
from ..services.runpod_client import RunPodClient
from .image_panel import ImagePanel
from .upload_worker import FileUploadResult, UploadWorker

logger = logging.getLogger(__name__)

_SETTINGS_ORG = "Digidoocs"
_SETTINGS_APP = "DocumentIntelligence"
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Document Intelligence")
        self.setMinimumSize(720, 480)
        self.resize(1100, 700)
        self._initial_geometry_applied = False

        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._runpod = RunPodClient()
        self._project: ProjectConfig | None = None
        self._image_paths: list[Path] = []
        self._row_fields: dict[int, dict[str, str]] = {}
        self._row_page_extractions: dict[int, list[list[FieldExtraction]]] = {}
        self._upload_active_row: int | None = None
        self._worker: UploadWorker | None = None

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._file_list.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        self._file_list.itemSelectionChanged.connect(self._on_row_selected)

        self._fields_show_all = False
        self._radio_current_page = QRadioButton("Current page")
        self._radio_all_fields = QRadioButton("All fields")
        self._radio_current_page.setChecked(True)
        self._fields_scope = QButtonGroup(self)
        self._fields_scope.addButton(self._radio_current_page)
        self._fields_scope.addButton(self._radio_all_fields)
        self._fields_scope.buttonClicked.connect(self._on_fields_scope_changed)

        scope_row = QHBoxLayout()
        scope_row.addWidget(self._radio_current_page)
        scope_row.addWidget(self._radio_all_fields)
        scope_row.addStretch()

        self._fields_table = QTableWidget(0, 2)
        self._fields_table.setHorizontalHeaderLabels(["Field", "Value"])
        self._apply_fields_table_resize_modes()
        self._fields_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fields_table.cellClicked.connect(self._on_fields_table_cell_clicked)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(8, 8, 8, 8)
        center_layout.addLayout(scope_row)
        center_layout.addWidget(self._fields_table, stretch=1)

        self._image_panel = ImagePanel()
        self._image_panel.setMinimumWidth(200)
        self._image_panel.page_index_changed.connect(self._on_viewer_page_changed)

        self._file_progress = QProgressBar()
        self._file_progress.setTextVisible(True)
        self._file_progress.setFormat("File %v of %m")
        self._file_progress.setVisible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.addWidget(self._file_list)
        left_layout.addWidget(self._file_progress)

        work_split = QSplitter(Qt.Orientation.Horizontal)
        work_split.addWidget(center_panel)
        work_split.addWidget(self._image_panel)
        work_split.setStretchFactor(0, 1)
        work_split.setStretchFactor(1, 1)
        work_split.setSizes([520, 360])

        root_split = QSplitter(Qt.Orientation.Horizontal)
        root_split.addWidget(left_panel)
        root_split.addWidget(work_split)
        root_split.setStretchFactor(0, 0)
        root_split.setStretchFactor(1, 1)
        root_split.setSizes([220, 900])
        self.setCentralWidget(root_split)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._refresh_status_text()

        self._build_menus()
        self._restore_session()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._initial_geometry_applied:
            return
        self._initial_geometry_applied = True
        self._fit_to_available_screen()

    def _fit_to_available_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 12
        max_w = max(self.minimumWidth(), available.width() - margin * 2)
        max_h = max(self.minimumHeight(), available.height() - margin * 2)
        width = min(self.width(), max_w)
        height = min(self.height(), max_h)
        self.resize(width, height)
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + margin
        self.move(x, y)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        load_config = QMenu("Load &Configuration", self)
        self._config_menu = load_config
        file_menu.addMenu(load_config)
        load_config.aboutToShow.connect(self._populate_config_menu)

        load_images = file_menu.addAction("Load &Images…")
        load_images.triggered.connect(self._load_images)

        upload = file_menu.addAction("&Upload")
        upload.triggered.connect(self._start_upload)

        file_menu.addSeparator()
        exit_action = file_menu.addAction("E&xit")
        exit_action.triggered.connect(self.close)

    def _populate_config_menu(self) -> None:
        self._config_menu.clear()
        projects = discover_project_configs()
        if not projects:
            root = config_directory()
            hint = (
                "Set FORM_CONFIG_DIRECTORY in .env"
                if root is None
                else f"No projects under {root}"
            )
            action = self._config_menu.addAction(hint)
            action.setEnabled(False)
            return
        for display_name, config_path in projects:
            action = self._config_menu.addAction(display_name)
            action.setData(str(config_path))
            action.triggered.connect(
                lambda checked, p=config_path: self._load_configuration(p)
            )

    def _load_configuration(self, config_path: Path) -> None:
        try:
            project = load_project_config(config_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Load configuration", str(exc))
            return
        self._project = project
        self._settings.setValue("last_config_path", str(config_path))
        self._rebuild_file_list()
        self._refresh_status_text()
        logger.info("Loaded project %s from %s", project.project_name, config_path)

    def _load_images(self) -> None:
        start_dir = ""
        if self._project and self._project.default_image_directory:
            d = self._project.default_image_directory
            if d.is_dir():
                start_dir = str(d)
        elif self._image_paths:
            start_dir = str(self._image_paths[0].parent)

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select images",
            start_dir,
            "Documents (*.pdf *.tif *.tiff *.png *.jpg *.jpeg);;All files (*.*)",
        )
        if not paths:
            return
        self._image_paths = [Path(p) for p in paths]
        self._row_fields.clear()
        self._row_page_extractions.clear()
        self._settings.setValue("image_paths", [str(p) for p in self._image_paths])
        self._rebuild_file_list()
        if self._image_paths:
            self._file_list.setCurrentRow(0)

    def _apply_fields_table_resize_modes(self) -> None:
        header = self._fields_table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self._fields_table.columnCount()):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )

    def _on_fields_scope_changed(self) -> None:
        self._fields_show_all = self._radio_all_fields.isChecked()
        if self._fields_show_all:
            self._fields_table.setColumnCount(3)
            self._fields_table.setHorizontalHeaderLabels(["Page", "Field", "Value"])
        else:
            self._fields_table.setColumnCount(2)
            self._fields_table.setHorizontalHeaderLabels(["Field", "Value"])
        self._apply_fields_table_resize_modes()
        row = self._current_file_row()
        if row is not None:
            self._show_fields_for_row(row)

    def _on_viewer_page_changed(self, _page_index: int) -> None:
        if self._fields_show_all:
            return
        row = self._current_file_row()
        if row is not None:
            self._show_fields_for_row(row)

    def _rebuild_file_list(self) -> None:
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance("filename.ext")
        for path in self._image_paths:
            width = max(width, metrics.horizontalAdvance(path.name))
        self._file_list.setFixedWidth(max(160, width + 28))
        self._file_list.clear()

        for row, path in enumerate(self._image_paths):
            self._hydrate_row_from_json(row, path)
            self._file_list.addItem(path.name)

        current = self._current_file_row()
        if current is not None:
            self._show_fields_for_row(current)

    def _hydrate_row_from_json(self, row: int, path: Path) -> None:
        pages = load_extraction_json(path)
        if pages is None:
            return
        self._row_page_extractions[row] = pages
        self._row_fields[row] = merge_extracted_fields(pages)

    def _on_row_selected(self) -> None:
        row = self._current_file_row()
        if row is None:
            return
        path = self._image_paths[row]
        self._image_panel.show_path(path)
        self._image_panel.clear_highlights()
        self._show_fields_for_row(row)

    def _show_fields_for_row(self, row: int) -> None:
        pages = self._row_page_extractions.get(row)
        rows: list[tuple[int, str, str]] = []
        if pages:
            if self._fields_show_all:
                for page_no, page in enumerate(pages, start=1):
                    for fe in sorted(page, key=vertical_sort_key):
                        rows.append((page_no, fe.name, fe.value))
            else:
                page_idx = self._image_panel.page_index()
                if 0 <= page_idx < len(pages):
                    page = pages[page_idx]
                    for fe in sorted(page, key=vertical_sort_key):
                        rows.append((page_idx + 1, fe.name, fe.value))
        elif row in self._row_fields:
            for key, value in sorted(self._row_fields[row].items()):
                rows.append((1, key, value))

        self._fields_table.setRowCount(len(rows))
        if self._fields_show_all:
            for i, (page_no, key, value) in enumerate(rows):
                self._fields_table.setItem(i, 0, QTableWidgetItem(str(page_no)))
                self._fields_table.setItem(i, 1, QTableWidgetItem(key))
                self._fields_table.setItem(i, 2, QTableWidgetItem(value))
        else:
            for i, (_page_no, key, value) in enumerate(rows):
                self._fields_table.setItem(i, 0, QTableWidgetItem(key))
                self._fields_table.setItem(i, 1, QTableWidgetItem(value))
        self._fields_table.resizeColumnsToContents()

    def _current_file_row(self) -> int | None:
        row = self._file_list.currentRow()
        if 0 <= row < len(self._image_paths):
            return row
        return None

    def _highlight_field(
        self, file_row: int, field_name: str, *, page_index: int | None = None
    ) -> None:
        pages = self._row_page_extractions.get(file_row, [])
        located = find_field_extraction(
            pages, field_name, page_index=page_index
        )
        path = self._image_paths[file_row]
        if not located:
            self._image_panel.show_path(path)
            self._image_panel.clear_highlights()
            return
        page_idx, extraction = located
        on_view = (
            self._image_panel.document_path() == path
            and self._image_panel.page_index() == page_idx
        )
        if not on_view:
            self._image_panel.show_page(path, page_idx, refit=False)
        self._image_panel.highlight_bboxes(
            extraction.label_bbox, extraction.value_bbox
        )

    def _on_fields_table_cell_clicked(self, row: int, column: int) -> None:
        file_row = self._current_file_row()
        if file_row is None:
            return
        if self._fields_show_all:
            page_item = self._fields_table.item(row, 0)
            name_item = self._fields_table.item(row, 1)
            if page_item is None or name_item is None:
                return
            try:
                page_index = int(page_item.text()) - 1
            except ValueError:
                page_index = 0
            field_name = name_item.text()
        else:
            name_item = self._fields_table.item(row, 0)
            if name_item is None:
                return
            field_name = name_item.text()
            page_index = self._image_panel.page_index()
        self._highlight_field(
            file_row, field_name, page_index=page_index
        )

    def _start_upload(self) -> None:
        if not self._image_paths:
            QMessageBox.information(self, "Upload", "Load images first.")
            return
        if not self._runpod.is_configured:
            QMessageBox.warning(
                self,
                "RunPod",
                "RunPod is not configured.\n" + self._runpod.missing_config_hint(),
            )
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "Upload", "Upload already in progress.")
            return

        index_fields = self._project.index_fields if self._project else []
        self._worker = UploadWorker(self._image_paths, index_fields, self._runpod)
        self._worker.file_started.connect(self._on_upload_file_started)
        self._worker.page_started.connect(self._on_upload_page_started)
        self._worker.page_completed.connect(self._on_upload_page_completed)
        self._worker.file_completed.connect(self._on_upload_completed)
        self._worker.file_failed.connect(self._on_upload_failed)
        self._worker.batch_finished.connect(self._on_upload_finished)
        total = len(self._image_paths)
        self._file_progress.setVisible(True)
        self._file_progress.setMaximum(total)
        self._file_progress.setValue(0)
        self._upload_active_row = None
        self._worker.start()
        self._status.showMessage("Uploading…")

    def _on_upload_file_started(self, row: int, page_count: int) -> None:
        self._upload_active_row = row
        self._row_page_extractions[row] = []
        path = self._image_paths[row]
        self._file_list.setCurrentRow(row)
        self._file_progress.setValue(row)
        self._image_panel.show_page(path, 0)
        self._image_panel.set_page_progress(0, page_count)
        self._show_fields_for_row(row)
        self._status.showMessage(f"Uploading {path.name}…")

    def _on_upload_page_started(self, row: int, page_index: int, page_count: int) -> None:
        if self._upload_active_row != row:
            return
        path = self._image_paths[row]
        self._image_panel.show_page(path, page_index)
        self._image_panel.set_page_progress(page_index, page_count)
        self._status.showMessage(
            f"Uploading {path.name} — page {page_index + 1} of {page_count}…"
        )

    def _on_upload_page_completed(self, row: int, page_index: int, fields: object) -> None:
        if not isinstance(fields, list):
            return
        extractions = [fe for fe in fields if isinstance(fe, FieldExtraction)]
        pages = self._row_page_extractions.setdefault(row, [])
        if page_index == len(pages):
            pages.append(extractions)
        elif page_index < len(pages):
            pages[page_index] = extractions
        else:
            pages.extend([] for _ in range(page_index - len(pages)))
            pages.append(extractions)
        if self._upload_active_row == row:
            self._show_fields_for_row(row)

    def _on_upload_completed(self, row: int, result: object) -> None:
        if not isinstance(result, FileUploadResult):
            return
        self._row_fields[row] = result.fields
        self._row_page_extractions[row] = result.page_fields
        self._file_progress.setValue(row + 1)
        if self._upload_active_row == row:
            self._show_fields_for_row(row)

    def _on_upload_failed(self, row: int, message: str) -> None:
        logger.error("Row %s failed: %s", row, message)
        item = self._file_list.item(row)
        if item is not None:
            item.setText(f"{self._image_paths[row].name} (error)")
        QMessageBox.warning(self, "Upload failed", message)

    def _on_upload_finished(self) -> None:
        self._file_progress.setVisible(False)
        self._image_panel.clear_page_progress()
        self._upload_active_row = None
        self._status.showMessage("Upload finished", 5000)
        self._worker = None

    def _refresh_status_text(self) -> None:
        parts = []
        if self._project:
            parts.append(f"Project: {self._project.project_name}")
        else:
            parts.append("No project loaded")
        if self._runpod.is_configured:
            mode = "pod" if self._runpod.host else "serverless"
            parts.append(f"RunPod ({mode}): {self._runpod.model}")
        else:
            parts.append("RunPod not configured")
        self._status.showMessage(" · ".join(parts))

    def _restore_session(self) -> None:
        config_raw = self._settings.value("last_config_path", "")
        if config_raw:
            config_path = Path(str(config_raw))
            if config_path.is_file():
                try:
                    self._project = load_project_config(config_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    logger.warning("Could not restore config %s", config_path)

        paths_raw = self._settings.value("image_paths", [])
        if isinstance(paths_raw, list):
            restored = [Path(str(p)) for p in paths_raw if Path(str(p)).is_file()]
            self._image_paths = restored

        self._rebuild_file_list()
        if self._image_paths:
            self._file_list.setCurrentRow(0)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)
