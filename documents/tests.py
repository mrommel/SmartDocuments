from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .extraction import extract_metadata
from .models import Collection, Document, Project, Tag


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

	@patch("documents.views.extract_metadata", return_value={"title": "Meeting", "summary": "Plans", "keywords": []})
	def test_upload_stores_original_and_metadata(self, extractor):
		collection = Collection.objects.create(project=self.project, name="Meetings")
		tag = Tag.objects.create(project=self.project, name="Important")
		response = self.upload(collections=[collection.pk], tags=[tag.pk])
		document = Document.objects.get()
		self.assertRedirects(response, reverse("document_detail", args=[self.project.pk, document.pk]))
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Meeting")
		self.assertEqual(document.file_size, 23)
		self.assertEqual(list(document.collections.all()), [collection])
		self.assertEqual(list(document.tags.all()), [tag])
		self.assertEqual(self.client.get(reverse("document_download", args=[self.project.pk, document.pk])).getvalue(), b"Meeting notes and plans")
		extractor.assert_called_once()

	@patch("documents.views.extract_metadata", side_effect=ValueError("Model unavailable"))
	def test_failed_extraction_can_retry(self, extractor):
		self.upload()
		document = Document.objects.get()
		self.assertEqual(document.status, Document.Status.FAILED)
		self.assertTrue(document.file.storage.exists(document.file.name))
		extractor.side_effect = None
		extractor.return_value = {"title": "Recovered"}
		self.client.post(reverse("document_retry", args=[self.project.pk, document.pk]))
		document.refresh_from_db()
		self.assertEqual(document.status, Document.Status.COMPLETE)
		self.assertEqual(document.metadata["title"], "Recovered")
		self.assertEqual(document.extraction_error, "")
		self.assertEqual(self.client.get(reverse("document_retry", args=[self.project.pk, document.pk])).status_code, 405)

	@patch("documents.views.extract_metadata", return_value={})
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
