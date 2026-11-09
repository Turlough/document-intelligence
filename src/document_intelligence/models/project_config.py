from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IndexField:
    name: str
    field_type: str = "str"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IndexField:
        return cls(
            name=str(raw.get("name", "")).strip(),
            field_type=str(raw.get("type", "str")).strip() or "str",
        )


@dataclass
class ProjectConfig:
    project_name: str
    config_path: Path
    default_image_directory: Path | None = None
    index_fields: list[IndexField] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any], config_path: Path) -> ProjectConfig:
        raw_dir = data.get("default_image_directory")
        default_dir: Path | None = None
        if raw_dir:
            default_dir = Path(str(raw_dir))
        fields = [
            IndexField.from_dict(item)
            for item in (data.get("index_fields") or [])
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        return cls(
            project_name=str(data.get("project_name", config_path.parent.name)).strip()
            or config_path.parent.name,
            config_path=config_path,
            default_image_directory=default_dir,
            index_fields=fields,
        )
