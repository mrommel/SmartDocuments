from django.urls import path
from django.views.generic import RedirectView
import documents.views as _pv

urlpatterns = [
	path('', RedirectView.as_view(url='dashboard', permanent=False), name='dashboard'),
	path('dashboard', _pv.dashboard, name='dashboard'),
]