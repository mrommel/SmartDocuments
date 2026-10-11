from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models


def document_path(instance, filename):
	return f"documents/{instance.project_id}/{uuid4().hex}{Path(filename).suffix.lower()}"


class Project(models.Model):
	name = models.CharField(max_length=120, unique=True)
	description = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.name


class Collection(models.Model):
	project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="collections")
	name = models.CharField(max_length=120)

	class Meta:
		constraints = [models.UniqueConstraint(fields=["project", "name"], name="unique_collection_per_project")]
		ordering = ["name"]

	def __str__(self):
		return self.name


class Tag(models.Model):
	project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tags")
	name = models.CharField(max_length=80)

	class Meta:
		constraints = [models.UniqueConstraint(fields=["project", "name"], name="unique_tag_per_project")]
		ordering = ["name"]

	def __str__(self):
		return self.name


class Document(models.Model):
	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		PROCESSING = "processing", "Processing"
		COMPLETE = "complete", "Complete"
		FAILED = "failed", "Failed"

	project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
	file = models.FileField(upload_to=document_path, max_length=500)
	original_name = models.CharField(max_length=255)
	file_size = models.PositiveBigIntegerField()
	uploaded_at = models.DateTimeField(auto_now_add=True)
	collections = models.ManyToManyField(Collection, blank=True, related_name="documents")
	tags = models.ManyToManyField(Tag, blank=True, related_name="documents")
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
	metadata = models.JSONField(default=dict, blank=True)
	extraction_error = models.TextField(blank=True)
	find_addresses = models.BooleanField(default=False)

	class Meta:
		ordering = ["-uploaded_at"]

	def __str__(self):
		return self.original_name

	def clean(self):
		super().clean()
		if self.pk:
			if self.collections.exclude(project_id=self.project_id).exists():
				raise ValidationError("Collections must belong to the document's project.")
			if self.tags.exclude(project_id=self.project_id).exists():
				raise ValidationError("Tags must belong to the document's project.")


class DocumentAddress(models.Model):
	class Category(models.TextChoices):
		CUSTOMER = "customer", "Customer"
		SHOP = "shop", "Shop"
		PRIVATE = "private", "Private"
		BUSINESS = "business", "Business"
		OTHER = "other", "Other"

	document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="addresses")
	address = models.CharField(max_length=255)
	category = models.CharField(max_length=12, choices=Category.choices, default=Category.OTHER)
	geocode_result = models.JSONField(null=True, blank=True)
	geocode_error = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ["pk"]

	def __str__(self):
		return self.address
