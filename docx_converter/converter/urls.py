from django.urls import path

from . import views

app_name = "converter"

urlpatterns = [
    path("", views.upload_docx, name="upload_docx"),
    path("result/<uuid:upload_id>/", views.result, name="result"),
    path("edit/<uuid:upload_id>/", views.edit_html, name="edit_html"),
    path(
        "download/<uuid:upload_id>/<str:file_type>/",
        views.download_file,
        name="download_file",
    ),
    path("upload_image/", views.upload_image, name="upload_image"),
    path("archive/", views.archive_view, name="archive"),
    path("download/pdf/<uuid:upload_id>/", views.download_pdf, name="download_pdf"),
    path("delete/<uuid:upload_id>/", views.delete_upload, name="delete_upload"),
]
