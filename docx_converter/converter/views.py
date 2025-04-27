import html
import logging
import os
import uuid

from bs4 import BeautifulSoup
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from weasyprint import CSS, HTML

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


def highlight_code(code, language):
    try:
        language_map = {
            "markup": "xml",
            "bash": "bash",
            "java": "java",
            "json": "json",
        }

        lexer_name = language_map.get(language, "xml")
        lexer = get_lexer_by_name(lexer_name)
        logger.debug(f"Using lexer: {lexer}")

        formatter = HtmlFormatter(
            cssclass="highlight",
            nowrap=False,
            style="default",
            full=True,
        )

        highlighted = highlight(code, lexer, formatter)

        return highlighted

    except Exception:
        return f'<code class="language-{language}">{html.escape(code)}</code>'


def download_pdf(request, upload_id):
    upload = get_object_or_404(DocumentUpload, id=upload_id)
    pdf_path = upload.html_file.path.replace(".html", ".pdf")

    with open(upload.html_file.path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")

    for element in soup.find_all(["script", "link"]):
        element.decompose()

    for img in soup.find_all("img"):
        if img["src"].startswith("/media/"):
            img["src"] = "file://" + os.path.join(settings.MEDIA_ROOT, img["src"][7:])

    for pre in soup.find_all("pre"):
        language = None
        for cls in pre.get("class", []):
            if cls.startswith("language-"):
                language = cls.replace("language-", "")
                break

        if not pre.code:
            code = soup.new_tag("code")
            code.string = pre.get_text()
            pre.clear()
            pre.append(code)

        elif language:
            try:
                code_contents = []
                for child in pre.code.contents:
                    if child.name is None:  # Текстовые узлы
                        code_contents.append(str(child))
                    elif child.name == "br":  # Сохраняем переносы строк
                        code_contents.append("\n")

                code_text = "".join(code_contents).strip()

                if code_text:  # Проверяем, что код не пустой
                    highlighted = highlight_code(code_text, language)

                    if highlighted:  # Проверяем результат подсветки
                        logger.debug(f"Highlighted code!!!: {highlighted}")
                        new_code = BeautifulSoup(highlighted, "html.parser").find(
                            "div", class_="highlight"
                        )
                        logger.debug(f"New code: {new_code}")
                        if new_code:  # Убеждаемся, что нашли code-блок
                            pre.replace_with(new_code)
                        else:
                            logger.warning(
                                f"No code block found in highlighted content for {language}"
                            )
                            pre.code["class"] = pre.code.get("class", []) + [
                                f"language-{language}"
                            ]
                    else:
                        logger.warning(
                            f"Highlighting returned empty content for {language}"
                        )
                        pre.code["class"] = pre.code.get("class", []) + [
                            f"language-{language}"
                        ]
                else:
                    logger.warning("Empty code block found")

            except Exception as e:
                logger.error(f"Error processing code block: {str(e)}")
                pre.code["class"] = pre.code.get("class", []) + [f"language-{language}"]

    css_files = [
        os.path.join(settings.STATIC_ROOT, "css", "styles.css"),
    ]

    css_content = ""
    for css_file in css_files:
        try:
            with open(css_file, "r", encoding="utf-8") as f:
                css_content += f.read() + "\n"
        except Exception as e:
            logger.error(f"Error loading CSS {css_file}: {str(e)}")

    pygments_css = HtmlFormatter().get_style_defs(".highlight")
    css_content += pygments_css

    style_tag = soup.new_tag("style")
    style_tag.string = css_content
    if not soup.head:
        soup.html.insert(0, soup.new_tag("head"))
    soup.head.append(style_tag)

    html = HTML(string=str(soup), base_url=settings.MEDIA_ROOT, encoding="utf-8")

    html.write_pdf(
        pdf_path,
        stylesheets=[CSS(string=css_content)],
    )

    with open(pdf_path, "rb") as f:
        response = HttpResponse(f.read(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(pdf_path)}"'
        )

    # Debugging
    with open(pdf_path.replace(".pdf", "_processed.html"), "w", encoding="utf-8") as f:
        f.write(str(soup))

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
