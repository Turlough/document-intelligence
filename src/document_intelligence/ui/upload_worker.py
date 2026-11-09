from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ..models.project_config import IndexField
from ..services.image_loader import image_to_png_bytes, load_first_page_image, placeholder_image
from ..services.response_parse import DEFAULT_EXTRACTION_PROMPT, parse_model_object, value_for_field
from ..services.runpod_client import RunPodClient

logger = logging.getLogger(__name__)


@dataclass
class FileUploadResult:
    path: Path
    raw_text: str
    fields: dict[str, str]
    error: str | None = None


class UploadWorker(QThread):
    file_started = pyqtSignal(int)
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
            self.file_started.emit(row)
            try:
                image = load_first_page_image(path)
                if image is None:
                    image = placeholder_image(path.name)
                png = image_to_png_bytes(image)
                raw = self._client.read_page(
                    self._prompt,
                    png,
                    should_cancel=self._should_cancel,
                )
                parsed = parse_model_object(raw)
                fields = dict(parsed) if parsed is not None else {"(raw response)": raw}
                for field in self._index_fields:
                    if field.name not in fields:
                        hit = value_for_field(fields, field.name)
                        if hit:
                            fields[field.name] = hit
                self.file_completed.emit(
                    row,
                    FileUploadResult(path=path, raw_text=raw, fields=fields),
                )
            except Exception as exc:
                logger.exception("Upload failed for %s", path)
                self.file_failed.emit(row, str(exc))
        self.batch_finished.emit()
