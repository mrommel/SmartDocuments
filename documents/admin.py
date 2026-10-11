from django.contrib import admin

from .models import Collection, Document, DocumentAddress, Project, Tag


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
	list_display = ("name", "created_at")
	search_fields = ("name",)


@admin.register(Collection, Tag)
class OrganizationAdmin(admin.ModelAdmin):
	list_display = ("name", "project")
	list_filter = ("project",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ("original_name", "project", "status", "uploaded_at")
	list_filter = ("project", "status")
	search_fields = ("original_name",)


@admin.register(DocumentAddress)
class DocumentAddressAdmin(admin.ModelAdmin):
	list_display = ("address", "category", "document", "geocode_error")
	list_filter = ("category",)
	search_fields = ("address", "document__original_name")
