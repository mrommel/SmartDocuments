from io import BytesIO
import os
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from unittest.mock import patch

import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django_tasks_db.models import DBTaskResult
from PIL import Image

from .extraction import _request, extract_metadata
from .models import Collection, Document, Project, Tag
from .tasks import analyze_document


class DocumentFlowTests(TestCase):
	def setUp(self):
		self.media = TemporaryDirectory()
		self.addCleanup(self.media.cleanup)
		self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
		self.settings_override.enable()
		self.addCleanup(self.settings_override.disable)
		self.project = Project.objects.create(name="Work")
		self.other = Project.objects.create(name="Private")

	def upload(self, **kwargs):
		data = {"file": SimpleUploadedFile("notes.txt", b"Meeting notes and plans")}
		data.update(kwargs)
		return self.client.post(reverse("document_upload", args=[self.project.pk]), data)

	@patch("documents.tasks.extract_metadata", return_value={"title": "Meeting", "summary": "Plans", "keywords": []})
	def test_upload_stores_original_and_metadata(self, extractor):
		collection = Collection.objects.create(project=self.project, name="Meetings")
		tag = Tag.objects.create(project=self.project, name="Important")
		with self.captureOnCommitCallbacks(execute=True):
			response = self.upload(collections=[collection.pk], tags=[tag.pk])
		document = Document.objects.get()
		self.assertRedirects(response, reverse("document_detail", args=[self.project.pk, document.pk]))
		self.assertEqual(document.status, Document.Status.PENDING)
		self.assertEqual(DBTaskResult.objects.count(), 1)
		extractor.assert_not_called()
		analyze_document.call(document.pk)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Meeting")
		self.assertEqual(document.file_size, 23)
		self.assertEqual(list(document.collections.all()), [collection])
		self.assertEqual(list(document.tags.all()), [tag])
		self.assertEqual(self.client.get(reverse("document_download", args=[self.project.pk, document.pk])).getvalue(), b"Meeting notes and plans")
		extractor.assert_called_once()

	@patch("documents.tasks.extract_metadata", side_effect=ValueError("Model unavailable"))
	def test_failed_extraction_can_retry(self, extractor):
		with self.captureOnCommitCallbacks(execute=True):
			self.upload()
		document = Document.objects.get()
		self.assertEqual(document.status, Document.Status.PENDING)
		with self.assertRaisesMessage(ValueError, "Model unavailable"), patch("documents.tasks.logger"):
			analyze_document.call(document.pk)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.FAILED)
		self.assertTrue(document.file.storage.exists(document.file.name))
		extractor.side_effect = None
		extractor.return_value = {"title": "Recovered"}
		with self.captureOnCommitCallbacks(execute=True):
			self.client.post(reverse("document_retry", args=[self.project.pk, document.pk]))
		self.assertEqual(DBTaskResult.objects.count(), 2)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.PENDING)
		analyze_document.call(document.pk)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Recovered")
		self.assertEqual(document.extraction_error, "")
		self.assertEqual(self.client.get(reverse("document_retry", args=[self.project.pk, document.pk])).status_code, 405)

	@patch("documents.tasks.extract_metadata", return_value={"title": "First analysis"})
	def test_completed_document_can_redo_analysis(self, extractor):
		with self.captureOnCommitCallbacks(execute=True):
			self.upload()
		document = Document.objects.get()
		detail = reverse("document_detail", args=[self.project.pk, document.pk])
		redo = reverse("document_retry", args=[self.project.pk, document.pk])
		self.assertNotContains(self.client.get(detail), "Re-do analysis")
		analyze_document.call(document.pk)
		document.refresh_from_db()
		self.assertContains(self.client.get(detail), "Re-do analysis")
		self.assertNotContains(self.client.get(detail), "Retry extraction")
		self.assertEqual(self.client.get(redo).status_code, 405)
		self.assertEqual(self.client.post(reverse("document_retry", args=[self.other.pk, document.pk])).status_code, 404)

		with self.captureOnCommitCallbacks(execute=True):
			response = self.client.post(redo)
		self.assertRedirects(response, detail)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.PENDING)
		self.assertEqual(document.metadata["title"], "First analysis")
		self.assertNotContains(self.client.get(detail), "Re-do analysis")
		self.assertEqual(DBTaskResult.objects.count(), 2)
		with self.captureOnCommitCallbacks(execute=True):
			self.client.post(redo)
		self.assertEqual(DBTaskResult.objects.count(), 2)

		extractor.return_value = {"title": "Updated analysis"}
		analyze_document.call(document.pk)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Updated analysis")
		self.assertContains(self.client.get(detail), "Re-do analysis")

	@patch("documents.tasks.extract_metadata", return_value={})
	def test_cross_project_assignments_rejected(self, extractor):
		foreign_tag = Tag.objects.create(project=self.other, name="Foreign")
		self.assertEqual(self.upload(tags=[foreign_tag.pk]).status_code, 200)
		self.assertFalse(Document.objects.exists())
		self.upload()
		document = Document.objects.get()
		detail_url = reverse("document_detail", args=[self.project.pk, document.pk])
		self.assertEqual(self.client.post(detail_url, {"tags": [foreign_tag.pk]}).status_code, 200)
		self.assertFalse(document.tags.exists())
		self.assertEqual(self.client.get(reverse("document_download", args=[self.other.pk, document.pk])).status_code, 404)

	def test_invalid_upload_and_missing_project(self):
		self.assertEqual(self.upload(file=SimpleUploadedFile("bad.exe", b"test")).status_code, 200)
		self.assertFalse(Document.objects.exists())
		self.assertEqual(self.client.get(reverse("document_upload", args=[9999])).status_code, 404)

	def test_image_uploads_queued_and_duplicate_retry_blocked(self):
		for extension, image_format in (("jpg", "JPEG"), ("png", "PNG"), ("tiff", "TIFF")):
			image = BytesIO()
			Image.new("RGB", (10, 10), "blue").save(image, format=image_format)
			with self.captureOnCommitCallbacks(execute=True):
				response = self.upload(file=SimpleUploadedFile(f"scan.{extension}", image.getvalue()))
			self.assertEqual(response.status_code, 302)
		self.assertEqual(Document.objects.count(), 3)
		self.assertEqual(DBTaskResult.objects.count(), 3)
		document = Document.objects.first()
		self.client.post(reverse("document_retry", args=[self.project.pk, document.pk]))
		self.assertEqual(DBTaskResult.objects.count(), 3)

	def test_project_navigation_and_duplicate_names(self):
		self.assertContains(self.client.get(reverse("dashboard")), "Work")
		self.assertContains(self.client.get(reverse("project_detail", args=[self.project.pk])), "Upload document")
		self.assertContains(self.client.get(reverse("document_upload", args=[self.project.pk])), "Project: ")
		self.client.post(reverse("project_create"), {"name": "New project"})
		self.assertTrue(Project.objects.filter(name="New project").exists())
		collection_url = reverse("collection_create", args=[self.project.pk])
		tag_url = reverse("tag_create", args=[self.project.pk])
		self.client.post(collection_url, {"name": "Letters"})
		self.client.post(tag_url, {"name": "Urgent"})
		self.assertContains(self.client.post(collection_url, {"name": "Letters"}), "already exists")
		self.assertContains(self.client.post(tag_url, {"name": "Urgent"}), "already exists")


class ExtractionTests(TestCase):
	def setUp(self):
		self.media = TemporaryDirectory()
		self.addCleanup(self.media.cleanup)
		settings_override = override_settings(MEDIA_ROOT=self.media.name)
		settings_override.enable()
		self.addCleanup(settings_override.disable)
		self.project = Project.objects.create(name="Scans")

	def asset(self, name, data):
		return Document.objects.create(
			project=self.project, file=SimpleUploadedFile(name, data),
			original_name=name, file_size=len(data),
		)

	def analyze_with_fake_llm(self, document):
		with patch("documents.extraction._request", side_effect=[
			{"data": [{"id": "vision-model"}]},
			{"choices": [{"message": {"content": '{"title":"Scanned","keywords":[]}'}}]},
		]) as request:
			metadata = extract_metadata(document)
		return metadata, request.call_args.args[1]["messages"][1]["content"]

	def test_empty_vision_response_is_not_success(self):
		image = BytesIO()
		Image.new("RGB", (12, 12), "blue").save(image, format="JPEG")
		document = self.asset("scan.jpeg", image.getvalue())
		with patch("documents.extraction._request", side_effect=[
			{"data": [{"id": "text-only-model"}]},
			{"choices": [{"message": {"content": '{"title":"","summary":"","document_type":"","date":"","keywords":[]}'}}]},
		]):
			with self.assertRaisesMessage(ValueError, "Load a vision-capable model"):
				extract_metadata(document)

	def test_image_formats_send_vision_content(self):
		for extension, image_format in (("jpg", "JPEG"), ("jpeg", "JPEG"), ("png", "PNG"), ("tif", "TIFF"), ("tiff", "TIFF")):
			image = BytesIO()
			Image.new("RGB", (12, 12), "blue").save(image, format=image_format)
			metadata, content = self.analyze_with_fake_llm(self.asset(f"scan.{extension}", image.getvalue()))
			self.assertEqual(metadata["title"], "Scanned")
			self.assertEqual(content[1]["type"], "image_url")
			self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

	def test_textless_pdf_falls_back_to_rendered_images(self):
		pdf = pymupdf.open()
		for _ in range(4):
			pdf.new_page()
		_, content = self.analyze_with_fake_llm(self.asset("scan.pdf", pdf.tobytes()))
		self.assertEqual(len(content), 4)
		self.assertEqual(content[1]["type"], "image_url")
		pdf.close()

	def test_pdf_with_text_keeps_text_route(self):
		pdf = pymupdf.open()
		pdf.new_page().insert_text((72, 72), "Readable PDF")
		_, content = self.analyze_with_fake_llm(self.asset("text.pdf", pdf.tobytes()))
		self.assertIn("Readable PDF", content)
		self.assertIsInstance(content, str)
		pdf.close()

	def test_local_chat_completions_json(self):
		class FakeDocument:
			original_name = "notes.txt"

		with patch("documents.extraction.read_text", return_value="An example document"), patch(
			"documents.extraction._request", side_effect=[
				{"data": [{"id": "local-model"}]},
				{"choices": [{"message": {"content": '{"title":"Example","summary":"A note","keywords":["note"]}'}}]},
			],
		) as request:
			result = extract_metadata(FakeDocument())
		self.assertEqual(result["title"], "Example")
		self.assertEqual(request.call_args.args[1]["model"], "local-model")

	def test_authenticated_model_and_chat_requests(self):
		requests = []

		def fake_urlopen(request, timeout):
			requests.append(request)
			if request.full_url.endswith("/models"):
				return BytesIO(b'{"data":[{"id":"local-model"}]}')
			return BytesIO(b'{"choices":[{"message":{"content":"{\\"title\\":\\"Example\\"}"}}]}')

		class FakeDocument:
			original_name = "notes.txt"

		with patch.dict(os.environ, {"OMLX_API_KEY": "test-secret", "OMLX_MODEL": ""}), patch(
			"documents.extraction.read_text", return_value="An example document"
		), patch("documents.extraction.urlopen", side_effect=fake_urlopen):
			self.assertEqual(extract_metadata(FakeDocument())["title"], "Example")

		self.assertEqual(len(requests), 2)
		for request in requests:
			self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")

	def test_chat_timeout_is_longer_than_model_discovery_and_configurable(self):
		class FakeDocument:
			original_name = "notes.txt"

		responses = [
			BytesIO(b'{"data":[{"id":"local-model"}]}'),
			BytesIO(b'{"choices":[{"message":{"content":"{\\"title\\":\\"Example\\"}"}}]}'),
		]
		with patch.dict(os.environ, {"OMLX_CHAT_TIMEOUT": "75"}), patch(
			"documents.extraction.read_text", return_value="An example document"
		), patch("documents.extraction.urlopen", side_effect=responses) as urlopen:
			extract_metadata(FakeDocument())
		self.assertEqual([call.kwargs["timeout"] for call in urlopen.call_args_list], [30, 75])

		with patch.dict(os.environ, {"OMLX_CHAT_TIMEOUT": ""}), patch(
			"documents.extraction.read_text", return_value="An example document"
		), patch("documents.extraction._request", return_value={"data": [{"id": "local-model"}]}) as request:
			with self.assertRaisesMessage(ValueError, "OMLX_CHAT_TIMEOUT must be a positive number"):
				extract_metadata(FakeDocument())
		self.assertEqual(request.call_count, 1)

	def test_timeout_error_explains_how_to_retry(self):
		with patch("documents.extraction.urlopen", side_effect=TimeoutError("timed out")):
			with self.assertRaisesMessage(ValueError, "timed out after 75 seconds") as caught:
				_request("http://127.0.0.1:8000/v1/chat/completions", {}, timeout=75)
		self.assertIn("OMLX_CHAT_TIMEOUT", str(caught.exception))

	def test_unauthorized_error_does_not_disclose_key(self):
		error = HTTPError("http://127.0.0.1:8000/v1/models", 401, "Unauthorized", {}, None)
		with patch.dict(os.environ, {"OMLX_API_KEY": "test-secret"}), patch(
			"documents.extraction.urlopen", side_effect=error
		):
			with self.assertRaisesMessage(ValueError, "Check OMLX_API_KEY in .env") as caught:
				_request("http://127.0.0.1:8000/v1/models")
		self.assertNotIn("test-secret", str(caught.exception))


class WorkerTests(TransactionTestCase):
	def setUp(self):
		self.media = TemporaryDirectory()
		self.addCleanup(self.media.cleanup)
		settings_override = override_settings(MEDIA_ROOT=self.media.name)
		settings_override.enable()
		self.addCleanup(settings_override.disable)

	@patch("documents.tasks.extract_metadata", return_value={"title": "Finished"})
	def test_database_worker_processes_queued_upload(self, extractor):
		project = Project.objects.create(name="Background")
		response = self.client.post(reverse("document_upload", args=[project.pk]), {
			"file": SimpleUploadedFile("letter.txt", b"Hello worker"),
		})
		self.assertEqual(response.status_code, 302)
		document = Document.objects.get()
		self.assertEqual(document.status, Document.Status.PENDING)
		extractor.assert_not_called()
		call_command("db_worker", batch=True, no_startup_delay=True, verbosity=0)
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Finished")

	@patch("documents.tasks.extract_metadata", side_effect=ValueError("Authentication rejected"))
	def test_database_worker_records_failed_analysis(self, extractor):
		project = Project.objects.create(name="Worker failure")
		self.client.post(reverse("document_upload", args=[project.pk]), {
			"file": SimpleUploadedFile("letter.txt", b"Hello worker"),
		})
		with patch("documents.tasks.logger"):
			call_command("db_worker", batch=True, no_startup_delay=True, verbosity=0)
		document = Document.objects.get()
		self.assertEqual(document.status, Document.Status.FAILED)
		self.assertIn("Authentication rejected", document.extraction_error)
		self.assertEqual(DBTaskResult.objects.get().status, "FAILED")
