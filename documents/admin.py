from django.contrib import admin

from .models import Collection, Document, Project, Tag


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
