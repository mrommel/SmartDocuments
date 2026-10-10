# Smart Documents

A Django service for storing documents within projects and extracting first-pass metadata with a local, OpenAI-compatible OMLX server.

## Start

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 9100
```

Open http://127.0.0.1:9100/. Start OMLX separately with a model loaded and its OpenAI-compatible API listening at `http://127.0.0.1:8000/v1`. The application selects the first model from `/v1/models`; set `OMLX_MODEL` to choose a specific model, or `OMLX_URL` to change the API base URL.

Create a project before uploading. Within each project you can create collections and tags, upload PDF, DOCX, TXT, MD, CSV or JSON files up to 10 MB, and add files to multiple collections and tags. The document details page displays the extracted title, summary, type, date and keywords. Files remain saved if extraction fails; use **Retry extraction** when the model is available again. Extraction runs during the upload request (up to two 30-second local API calls). Scanned PDFs without embedded text need OCR before uploading.

Run tests with `.venv/bin/python manage.py test documents`.

This starter app does not implement user authentication or per-user authorization. Protect the service behind authentication before exposing it to untrusted users, and do not serve the `media/` directory as public static files.
