# Agent guide

## Project

Smart Documents is a Django app for organizing uploaded files by project, collection, and tag, then extracting metadata through a local OpenAI-compatible OMLX API. The Django configuration is in `setup/`; the application is in `documents/`. See `README.md` for user-facing setup and limitations.

## Setup and checks

- Create a virtual environment and install dependencies: `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.
- Apply migrations: `.venv/bin/python manage.py migrate`.
- Run tests: `.venv/bin/python manage.py test documents`.
- Run the web app with `.venv/bin/python manage.py runserver 9100` and, in another terminal, the background worker with `.venv/bin/python manage.py db_worker`.
- If models change, create a migration with `.venv/bin/python manage.py makemigrations documents` and commit it alongside the model change. Avoid relying on the `make_migrations` Makefile target: its `sqlmigrate` step is hard-coded to migration `0001`.

## Code map and behavior

- `documents/models.py` defines projects, project-scoped collections and tags, documents, upload paths, and status values.
- `documents/forms.py` and `documents/views.py` handle uploads, project-scoped selections, document organization, and retry/re-analysis. Preserve cross-project validation.
- Uploads enqueue `analyze_document` from `documents/tasks.py` after transaction commit. Jobs live in SQLite via `django-tasks-db`; the separate `db_worker` process is required to process them. Keep task state transitions and retry behavior consistent.
- `documents/extraction.py` reads supported document types and talks to OMLX. Keep file-size limits, text/image handling, and timeout/error behavior intact when modifying extraction.
- `documents/templates/` and `documents/static/documents/` contain the server-rendered UI and styling. The README heading uses `documents/static/documents/favicon.svg`; keep the relative link working if this asset moves. URLs are defined in `documents/urls.py` and `setup/urls.py`.

## Configuration and tests

- The app reads a root `.env` file; process environment variables take precedence. OMLX settings include `OMLX_URL`, `OMLX_API_KEY`, `OMLX_MODEL`, and `OMLX_CHAT_TIMEOUT`. Never commit API keys or local `.env` files.
- Tests live in `documents/tests.py`. Mock OMLX requests rather than depending on a running model. Tests involving media should use temporary directories; tests involving tasks may need transaction-aware test cases or `captureOnCommitCallbacks()`.
- This starter app has no user authentication or per-user authorization. Do not expose it to untrusted users or serve `media/` as public static files without addressing access control.
