import os
import re
import uuid
import zipfile

import mammoth
from bs4 import BeautifulSoup
from django.conf import settings


def process_docx(docx_path, upload_id, original_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    # Очистка имени файла
    base_name = re.sub(r"[^\w\-]", "_", os.path.splitext(original_filename)[0])
    html_filename = f"{base_name}.html"
    zip_filename = f"{base_name}_images.zip"
    html_path = os.path.join(output_dir, html_filename)
    zip_path = os.path.join(output_dir, zip_filename)

    # Пользовательские стили
    style_map = """
        p[style-name='Warning'] => div.warning
        p[style-name='Important'] => div.important
        p[style-name='Code'] => pre.code
        h1 => h1.title
        h2 => h2.subtitle
    """

    # Обработка изображений
    def convert_image(image):
        ext = image.content_type.split("/")[-1]
        image_name = f"image_{uuid.uuid4().hex[:8]}.{ext}"
        image_path = os.path.join(images_dir, image_name)
        with image.open() as image_bytes:
            with open(image_path, "wb") as f:
                f.write(image_bytes.read())
        return {"src": f"/media/output/{upload_id}/images/{image_name}"}

    # Конвертация в HTML
    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_html(
            docx_file,
            style_map=style_map,
            convert_image=mammoth.images.img_element(convert_image),
        )
        html_content = result.value

    # Парсинг HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Обработка кода
    for tag in soup.find_all(["p", "pre"]):
        text = tag.get_text().strip()
        is_xml_like = (
            tag.name == "p"
            and text
            and re.match(r"^\s*<\w+\s+[^>]*>.*</\w+>\s*$", text)
        )
        if tag.name == "pre" or is_xml_like:
            new_pre = soup.new_tag("pre")
            new_pre["class"] = ["code", "language-xml"]
            new_code = soup.new_tag("code", attrs={"class": "language-xml"})
            new_code.string = text
            new_pre.append(new_code)
            tag.replace_with(new_pre)

    # Обработка таблиц
    for table in soup.find_all("table"):
        table["class"] = table.get("class", []) + ["default-bordered-table"]
        if "mce-item-table" in table["class"]:
            table["class"].remove("mce-item-table")
        # Проверка на <th> и стилизация первой строки
        has_th = bool(table.find("th"))
        if not has_th:
            first_tr = table.find("tr")
            if first_tr:
                for td in first_tr.find_all("td"):
                    td["class"] = td.get("class", []) + ["table-header"]

    # Создание HTML с минимальной обвязкой
    html_doc = BeautifulSoup(
        "<!DOCTYPE html><html><head></head><body></body></html>",
        "html.parser",
    )
    head = html_doc.head
    head.append(html_doc.new_tag("meta", charset="utf-8"))
    head.append(
        html_doc.new_tag(
            "link",
            rel="stylesheet",
            href="/static/js/tinymce/plugins/codesample/css/prism.css",
        )
    )
    head.append(
        html_doc.new_tag("link", rel="stylesheet", href="/static/css/styles.css")
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-core.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-markup.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-java.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-bash.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-json.js"
        )
    )
    html_doc.body.append(soup)

    # Сохранение HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc))

    # Создание ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(images_dir):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.join("images", file))

    return html_path, zip_path, str(html_doc), html_filename, zip_filename


def save_edited_html(html_content, upload_id, html_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    html_path = os.path.join(output_dir, html_filename)

    # Парсинг HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Очистка от старой обвязки
    if soup.head:
        soup.head.decompose()

    # Создание HTML с минимальной обвязкой
    html_doc = BeautifulSoup(
        "<!DOCTYPE html><html><head></head><body></body></html>",
        "html.parser",
    )
    head = html_doc.head
    head.append(html_doc.new_tag("meta", charset="utf-8"))
    head.append(
        html_doc.new_tag(
            "link",
            rel="stylesheet",
            href="/static/js/tinymce/plugins/codesample/css/prism.css",
        )
    )
    head.append(
        html_doc.new_tag("link", rel="stylesheet", href="/static/css/styles.css")
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-core.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-markup.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-java.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-bash.js"
        )
    )
    head.append(
        html_doc.new_tag(
            "script", src="/static/js/tinymce/plugins/codesample/js/prism-json.js"
        )
    )
    html_doc.body.append(soup)

    # Сохранение
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc))

    return html_path
