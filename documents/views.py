from pathlib import Path
import logging

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .extraction import extract_metadata
from .forms import CollectionForm, DocumentForm, OrganizationForm, ProjectForm, TagForm
from .models import Document, Project

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


def process_document(document):
	document.status = Document.Status.PENDING
	document.extraction_error = ""
	document.save(update_fields=["status", "extraction_error"])
	try:
		document.metadata = extract_metadata(document)
		document.status = Document.Status.COMPLETE
	except Exception as exc:
		logger.exception("Document metadata extraction failed for document %s", document.pk)
		document.status = Document.Status.FAILED
		document.extraction_error = str(exc)[:1000] if isinstance(exc, (ValueError, OSError)) else "Could not read document or contact local LLM."
	document.save(update_fields=["metadata", "status", "extraction_error"])


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
		process_document(document)
		if document.status == Document.Status.FAILED:
			messages.warning(request, "File saved, but metadata extraction failed. You can retry it later.")
		else:
			messages.success(request, "Document uploaded and metadata extracted.")
		return redirect("document_detail", pk=project.pk, document_id=document.pk)
	return render(request, "form.html", {
		"form": form, "project": project, "heading": "Upload document", "submit_label": "Upload and extract",
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
	return render(request, "document.html", {"document": document, "project": document.project, "form": form})


@require_POST
def document_retry(request, pk, document_id):
	document = _document(pk, document_id)
	process_document(document)
	if document.status == Document.Status.FAILED:
		messages.warning(request, "Metadata extraction failed again.")
	else:
		messages.success(request, "Metadata extracted successfully.")
	return redirect("document_detail", pk=pk, document_id=document_id)


def document_download(request, pk, document_id):
	document = _document(pk, document_id)
	return FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_name)
