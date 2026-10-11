from pathlib import Path
import logging

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CollectionForm, DocumentForm, OrganizationForm, ProjectForm, TagForm
from .models import Document, Project
from .tasks import analyze_document, retry_address_geocoding

logger = logging.getLogger(__name__)


def dashboard(request):
	return render(request, "dashboard.html", {"projects": Project.objects.all().order_by("name")})


def project_create(request):
	form = ProjectForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		project = form.save()
		messages.success(request, "Project created.")
		return redirect("project_detail", pk=project.pk)
	return render(request, "form.html", {"form": form, "heading": "New project", "submit_label": "Create project"})


def project_detail(request, pk):
	project = get_object_or_404(Project, pk=pk)
	documents = project.documents.prefetch_related("tags", "collections")
	collection_id = request.GET.get("collection")
	tag_id = request.GET.get("tag")
	if collection_id:
		documents = documents.filter(collections__pk=collection_id, collections__project=project)
	if tag_id:
		documents = documents.filter(tags__pk=tag_id, tags__project=project)
	return render(request, "project.html", {
		"project": project, "documents": documents.distinct(),
		"collections": project.collections.all(), "tags": project.tags.all(),
	})


def collection_create(request, pk):
	project = get_object_or_404(Project, pk=pk)
	form = CollectionForm(request.POST or None, project=project)
	if request.method == "POST" and form.is_valid():
		collection = form.save(commit=False)
		collection.project = project
		collection.save()
		messages.success(request, "Collection created.")
		return redirect("project_detail", pk=pk)
	return render(request, "form.html", {
		"form": form, "project": project, "heading": "New collection", "submit_label": "Create collection",
	})


def tag_create(request, pk):
	project = get_object_or_404(Project, pk=pk)
	form = TagForm(request.POST or None, project=project)
	if request.method == "POST" and form.is_valid():
		tag = form.save(commit=False)
		tag.project = project
		tag.save()
		messages.success(request, "Tag created.")
		return redirect("project_detail", pk=pk)
	return render(request, "form.html", {
		"form": form, "project": project, "heading": "New tag", "submit_label": "Create tag",
	})


def queue_document(document):
	document.status = Document.Status.PENDING
	document.extraction_error = ""
	document.save(update_fields=["status", "extraction_error"])

	def enqueue():
		try:
			analyze_document.enqueue(document.pk)
		except Exception:
			logger.exception("Could not queue analysis for document %s", document.pk)
			Document.objects.filter(pk=document.pk, status=Document.Status.PENDING).update(
				status=Document.Status.FAILED,
				extraction_error="Could not queue analysis. Check the task backend and retry.",
			)

	transaction.on_commit(enqueue)


def document_upload(request, pk):
	project = get_object_or_404(Project, pk=pk)
	form = DocumentForm(request.POST or None, request.FILES or None, project=project)
	if request.method == "POST" and form.is_valid():
		document = form.save(commit=False)
		document.project = project
		document.original_name = Path(form.cleaned_data["file"].name.replace("\\", "/")).name[:255]
		document.file_size = form.cleaned_data["file"].size
		document.save()
		form.save_m2m()
		queue_document(document)
		messages.success(request, "Document saved and queued for analysis. Refresh the page to see results.")
		return redirect("document_detail", pk=project.pk, document_id=document.pk)
	return render(request, "form.html", {
		"form": form, "project": project, "heading": "Upload document", "submit_label": "Upload and queue analysis",
		"upload": True,
	})


def _document(pk, document_id):
	return get_object_or_404(Document.objects.select_related("project"), pk=document_id, project_id=pk)


def document_detail(request, pk, document_id):
	document = _document(pk, document_id)
	form = OrganizationForm(request.POST or None, instance=document, project=document.project)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "Document organization updated.")
		return redirect("document_detail", pk=pk, document_id=document_id)
	return render(request, "document.html", {
		"document": document, "project": document.project, "form": form,
		"addresses": document.addresses.all(),
		"can_retry_geocoding": document.status == Document.Status.COMPLETE and
			document.addresses.filter(geocode_result__isnull=True).exists(),
	})

@require_POST
def document_retry(request, pk, document_id):
	document = _document(pk, document_id)
	if document.status in (Document.Status.PENDING, Document.Status.PROCESSING):
		messages.info(request, "Document analysis is already queued or in progress.")
	else:
		if "address_option" in request.POST:
			document.find_addresses = request.POST.get("find_addresses") == "on"
			document.save(update_fields=["find_addresses"])
		queue_document(document)
		messages.success(request, "Document queued for analysis again.")
	return redirect("document_detail", pk=pk, document_id=document_id)


@require_POST
def document_retry_geocoding(request, pk, document_id):
	document = _document(pk, document_id)
	if document.status != Document.Status.COMPLETE or not document.addresses.filter(geocode_result__isnull=True).exists():
		messages.info(request, "No address geocoding needs retrying right now.")
	else:
		def enqueue():
			try:
				retry_address_geocoding.enqueue(document.pk)
			except Exception:
				logger.exception("Could not queue address geocoding for document %s", document.pk)

		transaction.on_commit(enqueue)
		messages.success(request, "Address geocoding queued. Refresh this page to see results.")
	return redirect("document_detail", pk=pk, document_id=document_id)


def document_download(request, pk, document_id):
	document = _document(pk, document_id)
	return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_name)
