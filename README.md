# <img src="documents/static/documents/favicon.svg" alt="" width="32" height="32"> Smart Documents

A Django service for storing documents within projects and extracting first-pass metadata with a local, OpenAI-compatible OMLX server.

## Start

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 9100
```

Run the database task worker in a separate terminal (keep it running while using the site):

```sh
.venv/bin/python manage.py db_worker
```

Open http://127.0.0.1:9100/. Start OMLX separately with a model loaded and its OpenAI-compatible API listening at `http://127.0.0.1:8000/v1`. Django loads `.env` from the project root at startup (existing process environment variables take precedence). Set `OMLX_API_KEY` in `.env` to the key required by OMLX; it is sent as a Bearer token on both `/models` and `/chat/completions`. The application selects the first model from `/v1/models`; set `OMLX_MODEL` to choose a specific model, or `OMLX_URL` to change the API base URL. **Image and scanned-PDF analysis needs a vision-capable OMLX model** supporting OpenAI-style `image_url` messages. Configure `OMLX_MODEL` if the first loaded model cannot analyze images. Model discovery times out after 30 seconds; chat completion allows 600 seconds by default for slow local inference. Set `OMLX_CHAT_TIMEOUT` in `.env` to a positive number of seconds if inference needs longer. Restart the worker after changing `.env`, then retry failed documents.

Create a project before uploading. Within each project you can create collections and tags, upload PDF, DOCX, TXT, MD, CSV, JSON, JPEG, PNG or TIFF files up to 10 MB, and add files to multiple collections and tags. Uploads are queued in the database; the worker analyzes the document in the background. Refresh the document details page to see the extracted title, summary, type, date and keywords. Files remain saved if analysis fails; use **Retry extraction** when the model is available again. For completed documents, use **Re-do analysis** to queue a fresh analysis of the original file. Previous metadata stays visible until successful analysis replaces it. Textless PDFs are rendered to images (up to the first three pages) for vision analysis. Only the first frame of multi-page TIFFs is analyzed.

Select **Find and geocode addresses** when uploading a document, or change this option when retrying/re-doing analysis. The worker asks OMLX for addresses present in the document, categorizes each as customer, shop, private, business or other, and queries the local geocoder at `http://127.0.0.1:9112/api/geocode/` with the `text` query parameter. Run that service separately; set `GEOCODE_URL` in `.env` to override the endpoint and restart the worker. If the full street address has no match, the worker also tries its comma-separated city (without a Czech postal code). The first returned match is stored with each address and shown on the document details page; coordinates are **city-level, not house-level**. Missing matches and geocoder errors are displayed with the address without failing document analysis. Use **Retry geocoding** to queue another lookup of unmatched addresses without repeating LLM extraction. At most 20 distinct addresses per document are looked up. Re-analysis replaces old addresses only after successful metadata extraction; turning off the option clears them on successful re-analysis.

Run tests with `.venv/bin/python manage.py test documents`.

This starter app does not implement user authentication or per-user authorization. Protect the service behind authentication before exposing it to untrusted users, and do not serve the `media/` directory as public static files.
