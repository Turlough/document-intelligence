# document_intelligence package

## Purpose

PyQt6 desktop shell for Stage 1: load per-project JSON config, pick multipage scans, call RunPod Qwen3-VL once per page (merged per file), three-column UI — filename list, fields table, and image viewer (horizontal splitter between fields and viewer); compact **Page** / **Zoom** control groups on the viewer. Main window initial geometry fits the primary screen work area (above the taskbar).

## Ownership

- `main.py` — logging, `.env`, `QApplication`, `MainWindow`
- `models/` — `ProjectConfig`, `IndexField`
- `services/` — config discovery, image load, RunPod HTTP, JSON response parse
- `ui/` — layout, menus, `UploadWorker` on a background thread

## Local Contracts

- Project configs: subfolders of `FORM_CONFIG_DIRECTORY`, each containing `BASE_CONFIG_FILENAME` (default `config.json`)
- Upload prompt requests `fields[]` with `name`, `value`, `label_bbox`, `value_bbox` (Qwen 0–999); saved JSON: `{"pages": [{"fields": [...]}]}` as `{stem}.json`; `load_extraction_json` hydrates the file/field tables when that sidecar exists (load images, session restore, rebuild)
- PDF/multipage TIFF: one RunPod call per page; merged string values fill left index columns
- Centre field table: rows ordered top-to-bottom by Qwen label/value bbox (then left-to-right); **Field** and **Value** columns share width equally with word-wrapped text and row height from content; **All fields** mode keeps **Page** sized to contents; **Current page** vs **All fields** filters by viewer page; row click draws green label (dashed) / value (solid) boxes without changing zoom
- During upload: progress bars and live page preview (see prior UX notes)
- `QSettings` org `Digidoocs`, app `DocumentIntelligence` — keys `last_config_path`, `image_paths`
- Azure Document Intelligence and per-field Qwen prompts are out of scope until Stage 2

## Work Guidance

- New endpoints: add a client under `services/`, branch from `UploadWorker` / `MainWindow._start_upload`
- Index columns match parsed JSON keys case-insensitively via `value_for_field`

## Verification

- `uv sync` then `uv run python main.py`

## Child DOX Index

- `models/` — `ProjectConfig`, `FieldExtraction` (value + Qwen bboxes)
- `services/` — I/O and RunPod
- `ui/` — PyQt6 panels and workers
