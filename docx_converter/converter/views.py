import os
import uuid

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render

from .forms import DocumentUploadForm, HtmlEditForm
from .models import DocumentUpload
from .utils import process_docx, save_edited_html


def upload_docx(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload = DocumentUpload.objects.create(
                docx_file=form.cleaned_data["docx_file"]
            )
            original_filename = form.cleaned_data["docx_file"].name
            html_path, zip_path, html_content, html_filename, zip_filename = (
                process_docx(upload.docx_file.path, upload.id, original_filename)
            )
            upload.html_file = os.path.relpath(html_path, settings.MEDIA_ROOT)
            upload.images_zip = os.path.relpath(zip_path, settings.MEDIA_ROOT)
            upload.save()
            return render(
                request,
                "converter/result.html",
                {
                    "upload": upload,
                    "html_content": html_content,
                    "html_filename": html_filename,
                    "zip_filename": zip_filename,
                },
            )
    else:
        form = DocumentUploadForm()
    return render(request, "converter/upload.html", {"form": form})


def edit_html(request, upload_id):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    if request.method == "POST":
        form = HtmlEditForm(request.POST)
        if form.is_valid():
            html_content = form.cleaned_data["html_content"]
            html_path = save_edited_html(
                html_content, upload.id, os.path.basename(upload.html_file.name)
            )
            upload.html_file = os.path.relpath(html_path, settings.MEDIA_ROOT)
            upload.save()
            return render(
                request,
                "converter/result.html",
                {
                    "upload": upload,
                    "html_content": html_content,
                    "html_filename": os.path.basename(upload.html_file.name),
                    "zip_filename": os.path.basename(upload.images_zip.name),
                },
            )
    else:
        with open(upload.html_file.path, "r", encoding="utf-8") as f:
            html_content = f.read()
        form = HtmlEditForm(initial={"html_content": html_content})
    return render(
        request,
        "converter/edit.html",
        {
            "form": form,
            "upload": upload,
        },
    )


def download_file(request, upload_id, file_type):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    if file_type == "html":
        file_path = upload.html_file.path
    elif file_type == "zip":
        file_path = upload.images_zip.path
    else:
        return HttpResponse(status=404)
    with open(file_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/octet-stream")
        response["Content-Disposition"] = (
            f"attachment; filename={os.path.basename(file_path)}"
        )
        return response


def upload_image(request):
    if request.method == "POST" and request.FILES.get("file"):
        upload_id = request.POST.get("upload_id")
        upload = get_object_or_404(DocumentUpload, id=upload_id)
        image = request.FILES["file"]
        images_dir = os.path.join(
            settings.MEDIA_ROOT, "output", str(upload.id), "images"
        )
        os.makedirs(images_dir, exist_ok=True)
        image_name = f"uploaded_{uuid.uuid4().hex[:8]}{os.path.splitext(image.name)[1]}"
        image_path = os.path.join(images_dir, image_name)
        with open(image_path, "wb") as f:
            for chunk in image.chunks():
                f.write(chunk)
        image_url = f"/media/output/{upload.id}/images/{image_name}"
        return JsonResponse({"location": image_url})
    return JsonResponse({"error": "Invalid request"}, status=400)
