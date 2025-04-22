import html
import os
import re
import zipfile

import mammoth
from bs4 import BeautifulSoup
from django.conf import settings
from docx import Document


def process_docx(docx_path, upload_id, original_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    # Очистка имени файла
    base_name = re.sub(r"[^\w\-]", "_", os.path.splitext(original_filename)[0])
    html_filename = f"{base_name}.html"
    zip_filename = f"{base_name}_images.zip"

    # Пользовательские стили
    style_map = """
        p[style-name='Warning'] => div.warning
        p[style-name='Important'] => div.important
        p[style-name='Code'] => pre.code
        h1 => h1.title
        h2 => h2.subtitle
    """

    # Извлечение изображений
    def extract_images(docx_path, images_dir):
        doc = Document(docx_path)
        image_files = {}
        image_counter = 1

        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                image_data = rel.target_part.blob
                ext = ".png" if "png" in rel.target_ref.lower() else ".jpg"
                image_name = f"image_{image_counter}{ext}"
                image_path = os.path.join(images_dir, image_name)
                with open(image_path, "wb") as f:
                    f.write(image_data)
                image_files[rel.target_ref] = image_name
                image_counter += 1
        return image_files

    # Конвертация в HTML
    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file, style_map=style_map)
        html_content = result.value

    # Парсинг HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Обработка параграфов
    for tag in soup.find_all(["p", "pre"]):
        text = tag.get_text().strip()
        # Проверяем, является ли тег <pre> или <p> с чистым XML-подобным содержимым
        is_xml_like = (
            tag.name == "p"
            and text
            and re.match(r"^\s*<\w+\s+[^>]*>.*</\w+>\s*$", text)
        )
        if tag.name == "pre" or is_xml_like:
            # Заменяем <p> на <pre class="code">, если нужно
            if tag.name == "p":
                new_tag = soup.new_tag("pre")
                new_tag["class"] = ["code"]
                # Экранируем текст
                new_tag.string = html.escape(text)
                tag.replace_with(new_tag)
                tag = new_tag
            # Для <pre> экранируем содержимое
            if tag.string:
                tag.string = html.escape(tag.string)
            else:
                for child in tag.children:
                    if child.string:
                        child.string = html.escape(child.string)

    # Извлечение изображений
    image_files = extract_images(docx_path, images_dir)

    # Замена base64-изображений на ссылки
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("data:image"):
            for rel_ref, image_name in image_files.items():
                if rel_ref in src or image_name in src:
                    img["src"] = f"/media/output/{upload_id}/images/{image_name}"
                    break

    # Создание полной HTML-структуры
    html_doc = BeautifulSoup(
        '<!DOCTYPE html><html><head><link rel="stylesheet" href="/static/css/styles.css"></head><body></body></html>',
        "html.parser",
    )
    html_doc.body.append(soup)

    # Сохранение HTML
    html_path = os.path.join(output_dir, html_filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc.prettify()))

    # Создание ZIP-архива
    zip_path = os.path.join(output_dir, zip_filename)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(images_dir):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.join("images", file))

    return html_path, zip_path, str(html_doc), html_filename, zip_filename


def save_edited_html(html_content, upload_id, html_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    html_path = os.path.join(output_dir, html_filename)

    # Парсинг отредактированного HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Экранируем содержимое <pre>
    for pre in soup.find_all("pre"):
        if pre.string:
            pre.string = html.escape(pre.string)
        else:
            for child in pre.children:
                if child.string:
                    child.string = html.escape(child.string)

    # Создание полной HTML-структуры
    html_doc = BeautifulSoup(
        '<!DOCTYPE html><html><head><link rel="stylesheet" href="/static/css/styles.css"></head><body></body></html>',
        "html.parser",
    )
    html_doc.body.append(soup)

    # Сохранение
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc.prettify()))
    return html_path
