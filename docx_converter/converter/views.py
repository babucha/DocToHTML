import logging
import os
import uuid

from bs4 import BeautifulSoup
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from weasyprint import HTML

from .forms import DocumentUploadForm, HtmlEditForm
from .models import DocumentUpload
from .utils import process_docx, save_edited_html

logger = logging.getLogger(__name__)


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
            logger.debug(
                f"Uploaded document {upload.id}, HTML: {html_filename}, redirecting to edit"
            )
            return redirect("converter:edit_html", upload_id=upload.id)
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
            logger.debug(
                f"Saved edited HTML for upload {upload.id}, HTML: {os.path.basename(html_path)}"
            )
            return redirect("converter:result", upload_id=upload.id)
    else:
        with open(upload.html_file.path, "r", encoding="utf-8") as f:
            html_content = f.read()
        form = HtmlEditForm(initial={"html_content": html_content})
    logger.debug(f"Rendering edit.html for upload {upload.id}")
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
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        soup = BeautifulSoup(html_content, "html.parser")
        head = soup.new_tag("head")
        head.append(soup.new_tag("meta", charset="utf-8"))
        head.append(
            soup.new_tag(
                "meta",
                attrs={
                    "name": "viewport",
                    "content": "width=device-width, initial-scale=1.0",
                },
            )
        )
        head.append(soup.new_tag("title"))
        head.title.string = "Converted Document"
        head.append(
            soup.new_tag(
                "link",
                rel="stylesheet",
                href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
            )
        )
        head.append(
            soup.new_tag(
                "link",
                rel="stylesheet",
                href="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism.min.css",
            )
        )
        try:
            with open(
                os.path.join(settings.STATICFILES_DIRS[0], "css/styles.css"),
                "r",
                encoding="utf-8",
            ) as f:
                css_content = f.read()
        except FileNotFoundError:
            logger.error(f"styles.css not found in {settings.STATICFILES_DIRS[0]}")
            css_content = ""
        style = soup.new_tag("style")
        style.string = css_content
        head.append(style)
        head.append(
            soup.new_tag(
                "script",
                src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js",
            )
        )
        head.append(
            soup.new_tag(
                "script",
                src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-markup.min.js",
            )
        )
        head.append(
            soup.new_tag(
                "script",
                src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-java.min.js",
            )
        )
        head.append(
            soup.new_tag(
                "script",
                src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-bash.min.js",
            )
        )
        head.append(
            soup.new_tag(
                "script",
                src="https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/components/prism-json.min.js",
            )
        )
        if soup.head:
            soup.head.replace_with(head)
        else:
            soup.html.insert(0, head)
        body_content = soup.body.extract() if soup.body else soup
        new_body = soup.new_tag("body")
        container = soup.new_tag("div", attrs={"class": "container-sm mt-5"})
        container.append(body_content)
        new_body.append(container)
        if soup.html.body:
            soup.html.body.replace_with(new_body)
        else:
            soup.html.append(new_body)
        response = HttpResponse(str(soup), content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = (
            f"attachment; filename={os.path.basename(file_path)}"
        )
        return response
    elif file_type == "zip":
        file_path = upload.images_zip.path
        content_type = "application/zip"
        with open(file_path, "rb") as f:
            response = HttpResponse(f.read(), content_type=content_type)
            response["Content-Disposition"] = (
                f"attachment; filename={os.path.basename(file_path)}"
            )
            return response
    else:
        return HttpResponse(status=404)


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


def result(request, upload_id):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload.id))
    html_filename = os.path.basename(upload.html_file.name)
    zip_filename = os.path.basename(upload.images_zip.name)
    html_path = os.path.join(output_dir, html_filename)
    logger.debug(f"Attempting to open HTML file: {html_path}")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        logger.error(f"HTML file not found: {html_path}")
        return render(
            request, "converter/result.html", {"error": "HTML file not found"}
        )
    logger.debug(f"Rendering result.html for upload {upload_id}, HTML: {html_filename}")
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


def archive_view(request):
    query = request.GET.get("q", "")
    sort_by = request.GET.get("sort", "-uploaded_at")
    uploads = DocumentUpload.objects.all()
    if query:
        uploads = uploads.filter(docx_file__icontains=query)
    uploads = uploads.order_by(sort_by)
    return render(
        request,
        "converter/archive.html",
        {"uploads": uploads, "query": query, "sort": sort_by},
    )

def download_pdf(request, upload_id):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    pdf_path = upload.html_file.path.replace(".html", ".pdf")
    # Очищаем старый PDF
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        logger.debug(f"Removed old PDF: {pdf_path}")
    # Преобразуем HTML
    with open(upload.html_file.path, "r", encoding="utf-8") as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, "html.parser")
    # Удаляем все ссылки на CSS
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href", "")
        logger.debug(f"Removing stylesheet link: {href}")
        link.decompose()
    # Удаляем inline-стили для pre/code
    for tag in soup.find_all(["pre", "code"]):
        if tag.get("style"):
            logger.debug(f"Removing inline style from {tag.name}: {tag.get('style')}")
            del tag["style"]
    # Преобразуем пути для картинок
    for img in soup.find_all("img"):
        src = img.get("src", "")
        logger.debug(f"Original img src: {src}")
        if src.startswith("/media/"):
            relative_path = src[len("/media/") :]
            absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)
            img["src"] = absolute_path
            logger.debug(f"Converted img src: {absolute_path}")
    # Встраиваем styles.css
    try:
        with open(
            os.path.join(settings.STATICFILES_DIRS[0], "css", "styles.css"),
            "r",
            encoding="utf-8",
        ) as f:
            css_content = f.read()
    except FileNotFoundError:
        logger.error(f"styles.css not found in {settings.STATICFILES_DIRS[0]}")
        css_content = ""
    style_tag = soup.new_tag("style")
    style_tag.string = css_content
    if soup.head:
        soup.head.append(style_tag)
    else:
        head = soup.new_tag("head")
        head.append(style_tag)
        soup.insert(0, head)
    # Логируем и сохраняем HTML
    html_output = str(soup)
    logger.debug(f"Final HTML length: {len(html_output)}")
    with open(
        os.path.join(settings.MEDIA_ROOT, "debug_html.html"), "w", encoding="utf-8"
    ) as f:
        f.write(html_output)
    logger.debug(
        f"Saved HTML to {os.path.join(settings.MEDIA_ROOT, 'debug_html.html')}"
    )
    HTML(string=html_output, base_url=settings.MEDIA_ROOT).write_pdf(pdf_path)
    with open(pdf_path, "rb") as pdf_file:
        response = HttpResponse(pdf_file.read(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(upload.docx_file.name)}.pdf"'
        )
    return response

def delete_upload(request, upload_id):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    if request.method == "POST":
        try:
            if upload.html_file:
                os.remove(upload.html_file.path)
            if upload.images_zip:
                os.remove(upload.images_zip.path)
            if upload.docx_file:
                os.remove(upload.docx_file.path)
            upload.delete()
            logger.debug(f"Deleted upload {upload_id}")
        except Exception as e:
            logger.error(f"Error deleting upload {upload_id}: {e}")
        return redirect("converter:archive")
    return HttpResponse(status=405)
