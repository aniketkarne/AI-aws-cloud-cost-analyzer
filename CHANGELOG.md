# Changelog

All notable changes to this project are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Security
- `routes/ask.py` now sanitizes the LLM-generated SQL before execution
  via the new `sql_safety.sanitize_llm_sql` helper. Markdown code fences
  are stripped, only the first statement is kept, and anything other
  than `SELECT` / `WITH` / `SHOW` is rejected with HTTP 400. This closes
  the prompt-injection hole where an LLM-emitted `DROP TABLE cost_data`
  (or `SELECT 1; DROP TABLE …` smuggled after a `;`) would have been
  passed straight to `cursor.execute()`. `WITH` statements are parsed:
  the main statement after the CTE list must be a `SELECT`, because
  MySQL 8 permits CTEs before `UPDATE` / `DELETE` / `INSERT`. `INTO
  OUTFILE` / `INTO DUMPFILE` are rejected at any depth (SELECT can write
  files on the database host). Scanning is string-literal aware, so
  `;`, `--` and `#` inside quoted strings are preserved, not mangled.
  Rejected SQL is logged as a length + sha256 fingerprint, never raw.
  A 76-test pytest suite covers the sanitizer, the `/ask` and `/upload`
  routes and the startup wiring with mocked OpenAI/MySQL.
- `routes/upload.py` joined the raw multipart filename onto `/tmp`, so a
  crafted name like `../../etc/anything.csv` wrote anywhere the process
  could (and the extension check only verified the name's suffix). The
  upload now goes to a `tempfile.mkstemp()` path that is removed after
  parsing; the filename is used for the extension check only.

### Fixed
- `main.py`'s startup hook called `db.initialize_tables()` but only
  `initialize_tables` was imported, so every boot raised `NameError`
  and the backend never started. Now calls the imported name; a test
  pins the wiring.
- CORS: `allow_credentials=True` under `allow_origins=["*"]` is
  rejected by browsers (the spec forbids the combination) — dropped.
- `/upload` returned HTTP 500 for rejected file types: the generic
  exception handler swallowed the intended 400. `HTTPException` now
  passes through untouched.
- Model default updated from `gpt-4o-mini` to `gpt-6-luna`. OpenAI
  deprecated GPT-4o mini on 2026-10-14 (removal 2027-01-14) and lists
  `gpt-6-luna` as the recommended replacement. Updated in
  `routes/ask.py`, `.env.example`, and across the README (overview,
  tech stack, architecture diagram, config section).
- Backend failed to start: `backend/db.py` was missing — added the MySQL
  connection module (`get_connection`, `initialize_tables`) referenced by
  `main.py` and `routes/ask.py`.

### Added
- `backend/sql_safety.py` with `sanitize_llm_sql` and `UnsafeSQLError`.
- `tests/` directory with `conftest.py`, `test_sql_safety.py` (62
  unit tests over the sanitizer), `test_ask_endpoint.py` (9
  integration tests over the `/ask` route with mocked OpenAI + MySQL),
  and `test_upload_endpoint.py` (5 tests over `/upload` filename
  handling and temp-file cleanup).
- `pytest.ini` so `pytest` runs from the repo root without arguments.
- `.github/workflows/tests.yml` running the suite on Python 3.10 and
  3.12, plus an advisory `ruff` job that lists (but does not fail on)
  pre-existing style drift.
- `scripts/smoke_sql_safety.py` — runs 20 hand-crafted sanitizer cases
  with zero dependencies; useful for quick manual verification or as a
  reference for the policy.
- README "Testing" and "Security note on `/ask`" sections documenting
  how to run the suite and what the sanitizer guarantees.
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