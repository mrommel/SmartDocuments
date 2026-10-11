from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
	path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
	path("dashboard", views.dashboard, name="dashboard"),
	path("projects/new/", views.project_create, name="project_create"),
	path("projects/<int:pk>/", views.project_detail, name="project_detail"),
	path("projects/<int:pk>/collections/new/", views.collection_create, name="collection_create"),
	path("projects/<int:pk>/tags/new/", views.tag_create, name="tag_create"),
	path("projects/<int:pk>/upload/", views.document_upload, name="document_upload"),
	path("projects/<int:pk>/documents/<int:document_id>/", views.document_detail, name="document_detail"),
	path("projects/<int:pk>/documents/<int:document_id>/download/", views.document_download, name="document_download"),
	path("projects/<int:pk>/documents/<int:document_id>/retry/", views.document_retry, name="document_retry"),
	path("projects/<int:pk>/documents/<int:document_id>/retry-geocoding/", views.document_retry_geocoding, name="document_retry_geocoding"),
]