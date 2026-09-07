# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Fixed
- Backend failed to start: `backend/db.py` was missing — added the MySQL
  connection module (`get_connection`, `initialize_tables`) referenced by
  `main.py` and `routes/ask.py`.
- `routes/ask.py` used the deprecated `openai.ChatCompletion.create(...)`
  API that was removed in `openai>=1.0`. Migrated to the modern
  `client.chat.completions.create(...)` API and bumped the model to
  `gpt-4o-mini` (configurable via `OPENAI_MODEL`).
- `requirements.txt` pinned `pandas` (previously unpinned) and constrained
  `fastapi`, `uvicorn`, `mysql-connector-python`, `openai`, and `pydantic`
  to compatible ranges.
- `main.py` now resolves the `backend` package whether you run
  `python main.py` from `backend/` or `uvicorn backend.main:app` from the
  repo root.

### Added
- `LICENSE` file (MIT) — the README claimed MIT but the file was missing,
  so GitHub could not detect the license.
- `.env.example` documenting required `OPENAI_API_KEY` and MySQL variables.
- `.gitignore` covering Python (`__pycache__`, `venv/`, `.pytest_cache`),
  Next.js (`node_modules/`, `.next/`), secrets (`.env`), and editor noise
  (`.DS_Store`, `.vscode/`, `.idea/`).

### Changed
- README clone URL corrected to `aniketkarne/AI-aws-cloud-cost-analyzer`.
- README removed the unsupported "PDF upload" claim — `routes/upload.py`
  only accepts `.csv`, `.xls`, `.xlsx`.
- README aligned the LLM model across the doc (`gpt-4o-mini`).

### Removed
- Tracked `__pycache__/` directories under `backend/` (cleanup).