from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models.field_extraction import FieldExtraction
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
    value_for_field,
)
from ..services.runpod_client import RunPodClient
from .image_panel import ImagePanel
from .upload_worker import FileUploadResult, UploadWorker

logger = logging.getLogger(__name__)

_SETTINGS_ORG = "Digidoocs"
_SETTINGS_APP = "DocumentIntelligence"
_COL_FILENAME = "File"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Document Intelligence")
        self.resize(1280, 800)

        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._runpod = RunPodClient()
        self._project: ProjectConfig | None = None
        self._image_paths: list[Path] = []
        self._row_fields: dict[int, dict[str, str]] = {}
        self._row_page_extractions: dict[int, list[list[FieldExtraction]]] = {}
        self._upload_active_row: int | None = None
        self._worker: UploadWorker | None = None

        self._file_table = QTableWidget()
        self._file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._file_table.itemSelectionChanged.connect(self._on_row_selected)
        self._file_table.cellClicked.connect(self._on_file_table_cell_clicked)

        self._image_panel = ImagePanel()
        self._fields_table = QTableWidget(0, 3)
        self._fields_table.setHorizontalHeaderLabels(["Page", "Field", "Value"])
        header = self._fields_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._fields_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fields_table.cellClicked.connect(self._on_fields_table_cell_clicked)

        fields_header = QLabel("Extracted fields")
        right_bottom = QWidget()
        right_bottom_layout = QVBoxLayout(right_bottom)
        right_bottom_layout.setContentsMargins(0, 0, 0, 0)
        right_bottom_layout.addWidget(fields_header)
        right_bottom_layout.addWidget(self._fields_table)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(self._image_panel)
        right_split.addWidget(right_bottom)
        right_split.setStretchFactor(0, 3)
        right_split.setStretchFactor(1, 1)

        self._file_progress = QProgressBar()
        self._file_progress.setTextVisible(True)
        self._file_progress.setFormat("File %v of %m")
        self._file_progress.setVisible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._file_table)
        left_layout.addWidget(self._file_progress)

        root_split = QSplitter(Qt.Orientation.Horizontal)
        root_split.addWidget(left_panel)
        root_split.addWidget(right_split)
        root_split.setStretchFactor(0, 2)
        root_split.setStretchFactor(1, 3)
        self.setCentralWidget(root_split)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._refresh_status_text()

        self._build_menus()
        self._restore_session()

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
        self._rebuild_file_table()
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
        self._rebuild_file_table()
        if self._image_paths:
            self._file_table.selectRow(0)

    def _rebuild_file_table(self) -> None:
        headers = [_COL_FILENAME]
        if self._project:
            headers.extend(f.name for f in self._project.index_fields)

        self._file_table.setColumnCount(len(headers))
        self._file_table.setHorizontalHeaderLabels(headers)
        self._file_table.setRowCount(len(self._image_paths))

        for row, path in enumerate(self._image_paths):
            self._hydrate_row_from_json(row, path)
            self._file_table.setItem(row, 0, QTableWidgetItem(path.name))
            fields = self._row_fields.get(row, {})
            for col, field in enumerate(self._project.index_fields if self._project else [], start=1):
                value = value_for_field(fields, field.name)
                self._file_table.setItem(row, col, QTableWidgetItem(value))

        self._file_table.resizeColumnsToContents()
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
        rows = self._file_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._image_paths):
            return
        path = self._image_paths[row]
        self._image_panel.show_path(path)
        self._image_panel.clear_highlights()
        self._show_fields_for_row(row)

    def _show_fields_for_row(self, row: int) -> None:
        pages = self._row_page_extractions.get(row)
        rows: list[tuple[int, str, str]] = []
        if pages:
            for page_no, page in enumerate(pages, start=1):
                for fe in sorted(page, key=lambda f: f.name.casefold()):
                    rows.append((page_no, fe.name, fe.value))
        elif row in self._row_fields:
            for key, value in sorted(self._row_fields[row].items()):
                rows.append((1, key, value))
        self._fields_table.setRowCount(len(rows))
        for i, (page_no, key, value) in enumerate(rows):
            self._fields_table.setItem(i, 0, QTableWidgetItem(str(page_no)))
            self._fields_table.setItem(i, 1, QTableWidgetItem(key))
            self._fields_table.setItem(i, 2, QTableWidgetItem(value))

    def _current_file_row(self) -> int | None:
        rows = self._file_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
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
        self._image_panel.show_page(path, page_idx)
        self._image_panel.highlight_bboxes(
            extraction.label_bbox, extraction.value_bbox
        )

    def _on_file_table_cell_clicked(self, row: int, column: int) -> None:
        if column < 1 or row < 0 or row >= len(self._image_paths):
            return
        header = self._file_table.horizontalHeaderItem(column)
        if header is None:
            return
        field_name = header.text()
        self._highlight_field(row, field_name)

    def _on_fields_table_cell_clicked(self, row: int, column: int) -> None:
        file_row = self._current_file_row()
        if file_row is None:
            return
        page_item = self._fields_table.item(row, 0)
        name_item = self._fields_table.item(row, 1)
        if page_item is None or name_item is None:
            return
        try:
            page_index = int(page_item.text()) - 1
        except ValueError:
            page_index = 0
        self._highlight_field(
            file_row, name_item.text(), page_index=page_index
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
        self._file_table.selectRow(row)
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
        for col, field in enumerate(self._project.index_fields if self._project else [], start=1):
            value = value_for_field(result.fields, field.name)
            self._file_table.setItem(row, col, QTableWidgetItem(value))
        if self._upload_active_row == row:
            self._show_fields_for_row(row)

    def _on_upload_failed(self, row: int, message: str) -> None:
        logger.error("Row %s failed: %s", row, message)
        self._file_table.setItem(row, 0, QTableWidgetItem(f"{self._image_paths[row].name} (error)"))
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

        self._rebuild_file_table()
        if self._image_paths:
            self._file_table.selectRow(0)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)
