# document_intelligence package

## Purpose

PyQt6 desktop shell for Stage 1: load per-project JSON config, pick multipage scans, call RunPod Qwen3-VL once per page (merged per file), show parsed fields in the right-hand table and optional index columns.

## Ownership

- `main.py` — logging, `.env`, `QApplication`, `MainWindow`
- `models/` — `ProjectConfig`, `IndexField`
- `services/` — config discovery, image load, RunPod HTTP, JSON response parse
- `ui/` — layout, menus, `UploadWorker` on a background thread

## Local Contracts

- Project configs: subfolders of `FORM_CONFIG_DIRECTORY`, each containing `BASE_CONFIG_FILENAME` (default `config.json`)
- Upload uses `DEFAULT_EXTRACTION_PROMPT` in `response_parse.py`; PDF/multipage TIFF: one RunPod call per page; merged fields fill index columns; saved JSON is `{"pages": [<per-page field maps>]}` as `{stem}.json` beside each source
- During upload: file list + image viewer follow the active file/page; file- and page-level `QProgressBar`s under the list and image panel; fields table columns Page / Field / Value sorted by page
- Non-JSON page replies appear as `(raw response)` on that page row
- `QSettings` org `Digidoocs`, app `DocumentIntelligence` — keys `last_config_path`, `image_paths`
- Azure Document Intelligence and per-field Qwen prompts are out of scope until Stage 2

## Work Guidance

- New endpoints: add a client under `services/`, branch from `UploadWorker` / `MainWindow._start_upload`
- Index columns match parsed JSON keys case-insensitively via `value_for_field`

## Verification

- `uv sync` then `uv run python main.py`

## Child DOX Index

- `models/` — project JSON schema
- `services/` — I/O and RunPod
- `ui/` — PyQt6 panels and workers
