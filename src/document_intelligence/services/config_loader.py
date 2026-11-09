from __future__ import annotations

import json
import os
from pathlib import Path

from ..models.project_config import ProjectConfig


def config_directory() -> Path | None:
    raw = os.environ.get("FORM_CONFIG_DIRECTORY", "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def base_config_filename() -> str:
    return os.environ.get("BASE_CONFIG_FILENAME", "config.json").strip() or "config.json"


def discover_project_configs() -> list[tuple[str, Path]]:
    """Return ``(display_name, config_path)`` for each project subdirectory."""
    root = config_directory()
    if root is None:
        return []
    filename = base_config_filename()
    out: list[tuple[str, Path]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        candidate = child / filename
        if candidate.is_file():
            out.append((child.name, candidate))
    return out


def load_project_config(config_path: Path) -> ProjectConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Project config must be a JSON object")
    return ProjectConfig.from_json(data, config_path)
