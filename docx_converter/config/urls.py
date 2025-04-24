# docx_converter/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("converter.urls", namespace="converter")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
