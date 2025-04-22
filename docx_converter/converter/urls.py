from django.urls import path
from . import views

urlpatterns = [
    path("", views.upload_docx, name="upload_docx"),
    path("edit/<uuid:upload_id>/", views.edit_html, name="edit_html"),
    path(
        "download/<uuid:upload_id>/<str:file_type>/",
        views.download_file,
        name="download_file",
    ),
    path("upload_image/", views.upload_image, name="upload_image"),
]
