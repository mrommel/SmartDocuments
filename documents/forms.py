from pathlib import Path

from django import forms

from .extraction import MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS
from .models import Collection, Document, Project, Tag


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description"]


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["name"]

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_name(self):
        name = self.cleaned_data["name"]
        if self.project.collections.filter(name=name).exists():
            raise forms.ValidationError("This collection already exists in the project.")
        return name


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

    def clean_name(self):
        name = self.cleaned_data["name"]
        if self.project.tags.filter(name=name).exists():
            raise forms.ValidationError("This tag already exists in the project.")
        return name


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "collections", "tags", "find_addresses"]
        labels = {"find_addresses": "Find and geocode addresses"}
        help_texts = {"find_addresses": "Categorize addresses found in the document and look up city-level coordinates."}
        widgets = {
            "collections": forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collections"].queryset = project.collections.all()
        self.fields["tags"].queryset = project.tags.all()
        self.fields["file"].widget.attrs["accept"] = ",".join(sorted(SUPPORTED_EXTENSIONS))

    def clean_file(self):
        asset = self.cleaned_data["file"]
        if Path(asset.name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise forms.ValidationError("Supported formats: PDF, DOCX, TXT, MD, CSV, JSON, JPEG, PNG and TIFF.")
        if asset.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("Files must be 10 MB or smaller.")
        return asset


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["collections", "tags"]
        widgets = {
            "collections": forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
            "tags": forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collections"].queryset = project.collections.all()
        self.fields["tags"].queryset = project.tags.all()

