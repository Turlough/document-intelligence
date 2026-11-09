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
- Upload uses `DEFAULT_EXTRACTION_PROMPT` in `response_parse.py`; PDF/multipage TIFF: one RunPod call per page, fields merged with `merge_extracted_fields` (first non-empty wins); writes `{stem}.json` beside each source file
- Non-JSON page replies appear under `(raw response page N)` until merge
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
