from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ..models.project_config import IndexField
from ..services.image_loader import (
    document_page_count,
    image_to_png_bytes,
    load_document_page,
    placeholder_image,
)
from ..services.response_parse import (
    DEFAULT_EXTRACTION_PROMPT,
    extraction_prompt_for_page,
    merge_extracted_fields,
    parse_model_object,
    value_for_field,
    write_extraction_json,
)
from ..services.runpod_client import RunPodClient

logger = logging.getLogger(__name__)


@dataclass
class FileUploadResult:
    path: Path
    raw_text: str
    fields: dict[str, str]
    page_fields: list[dict[str, str]]
    json_path: Path | None = None
    error: str | None = None


class UploadWorker(QThread):
    file_started = pyqtSignal(int, int)
    page_started = pyqtSignal(int, int, int)
    page_completed = pyqtSignal(int, int, object)
    file_completed = pyqtSignal(int, object)
    file_failed = pyqtSignal(int, str)
    batch_finished = pyqtSignal()

    def __init__(
        self,
        paths: list[Path],
        index_fields: list[IndexField],
        client: RunPodClient,
        prompt: str = DEFAULT_EXTRACTION_PROMPT,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._paths = paths
        self._index_fields = index_fields
        self._client = client
        self._prompt = prompt
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _should_cancel(self) -> bool:
        return self._stop

    def run(self) -> None:
        for row, path in enumerate(self._paths):
            if self._stop:
                break
            page_count = document_page_count(path)
            self.file_started.emit(row, page_count)
            try:
                page_maps: list[dict[str, str]] = []
                raw_parts: list[str] = []
                for page_index in range(page_count):
                    if self._should_cancel():
                        raise InterruptedError("Cancelled")
                    self.page_started.emit(row, page_index, page_count)
                    image = load_document_page(path, page_index)
                    if image is None:
                        image = placeholder_image(
                            f"{path.name} page {page_index + 1}/{page_count}"
                        )
                    png = image_to_png_bytes(image)
                    prompt = extraction_prompt_for_page(
                        page_index, page_count, self._prompt
                    )
                    raw = self._client.read_page(
                        prompt,
                        png,
                        should_cancel=self._should_cancel,
                    )
                    raw_parts.append(raw)
                    parsed = parse_model_object(raw)
                    if parsed is None:
                        page_fields = {"(raw response)": raw}
                    else:
                        page_fields = parsed
                    page_maps.append(page_fields)
                    self.page_completed.emit(row, page_index, page_fields)

                fields = merge_extracted_fields(page_maps)
                if not fields and page_maps:
                    fields = dict(page_maps[0])
                for field in self._index_fields:
                    if field.name not in fields:
                        hit = value_for_field(fields, field.name)
                        if hit:
                            fields[field.name] = hit
                json_path = write_extraction_json(path, page_maps)
                raw_text = "\n\n".join(raw_parts)
                self.file_completed.emit(
                    row,
                    FileUploadResult(
                        path=path,
                        raw_text=raw_text,
                        fields=fields,
                        page_fields=page_maps,
                        json_path=json_path,
                    ),
                )
            except Exception as exc:
                logger.exception("Upload failed for %s", path)
                self.file_failed.emit(row, str(exc))
        self.batch_finished.emit()
