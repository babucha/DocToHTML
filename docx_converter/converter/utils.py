import os
import re
import uuid
import zipfile
from html import unescape

import mammoth
from bs4 import BeautifulSoup
from django.conf import settings


def process_docx(docx_path, upload_id, original_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    base_name = re.sub(r"[^\w\-]", "_", os.path.splitext(original_filename)[0])
    html_filename = f"{base_name}.html"
    zip_filename = f"{base_name}_images.zip"
    html_path = os.path.join(output_dir, html_filename)
    zip_path = os.path.join(output_dir, zip_filename)

    style_map = """
        p[style-name='Warning'] => div.warning
        p[style-name='Important'] => div.important
        p[style-name='Code'] => pre.code
        h1 => h1.title
        h2 => h2.subtitle
    """

    def convert_image(image):
        ext = image.content_type.split("/")[-1]
        image_name = f"image_{uuid.uuid4().hex[:8]}.{ext}"
        image_path = os.path.join(images_dir, image_name)
        with image.open() as image_bytes:
            with open(image_path, "wb") as f:
                f.write(image_bytes.read())
        return {"src": f"/media/output/{upload_id}/images/{image_name}"}

    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_html(
            docx_file,
            style_map=style_map,
            convert_image=mammoth.images.img_element(convert_image),
        )
        html_content = result.value

    soup = BeautifulSoup(html_content, "html.parser")

    def is_xml_like(text):
        text = text.strip()
        html_tags = ["p", "b", "i", "div", "span", "a", "strong", "em"]
        return bool(
            text
            and (
                re.match(r"^\s*<\w+\b[^>]*>.*</\w+>\s*$", text, re.DOTALL)
                or re.search(r"<\w+\b[^>]*>|</\w+>|<\?[\w-]+", text)
            )
            and not any(
                re.match(rf"^\s*<{tag}\b", text, re.IGNORECASE) for tag in html_tags
            )
        )

    # Обработка параграфов и pre
    for tag in soup.find_all(["p", "pre"]):
        text = tag.get_text().strip()
        if tag.name == "pre" or is_xml_like(text):
            new_pre = soup.new_tag("pre")
            new_pre["class"] = ["code", "language-markup"]
            new_code = soup.new_tag("code", attrs={"class": "language-markup"})
            new_code.string = text
            new_pre.append(new_code)
            tag.replace_with(new_pre)

    # Объединяем последовательные <pre> вне таблиц
    pre_tags = soup.find_all("pre", recursive=True)
    i = 0
    while i < len(pre_tags):
        current_pre = pre_tags[i]
        if current_pre.find_parent("table") is None:
            xml_content = [current_pre.code.text]
            j = i + 1
            while j < len(pre_tags) and pre_tags[j].find_parent("table") is None:
                # Пропускаем незначительные элементы (пустые <p>, <br>)
                prev_sibling = pre_tags[j].find_previous_sibling()
                if (
                    prev_sibling is None
                    or prev_sibling.name in ["pre", "br"]
                    or (
                        prev_sibling.name == "p" and not prev_sibling.get_text().strip()
                    )
                ):
                    xml_content.append(pre_tags[j].code.text)
                    pre_tags[j].decompose()
                    j += 1
                else:
                    break
            current_pre.code.string = "\n".join(xml_content)
            print(f"Non-table pre content: {xml_content}")
            i = j
        else:
            i += 1

    # Обработка таблиц
    for table in soup.find_all("table"):
        table["class"] = table.get("class", []) + ["default-bordered-table"]
        if "mce-item-table" in table["class"]:
            table["class"].remove("mce-item-table")
        has_th = bool(table.find("th"))
        if not has_th:
            first_tr = table.find("tr")
            if first_tr:
                for td in first_tr.find_all("td"):
                    td["class"] = td.get("class", []) + ["table-header"]
        for td in table.find_all("td"):
            xml_content = []
            non_xml_content = []
            print(f"TD children: {[child for child in td.children]}")
            for child in td.children:
                child_text = unescape(child.get_text().strip())
                if child_text:
                    if is_xml_like(child_text):
                        xml_content.append(child_text)
                    elif re.match(r"^\s*-+\s*$", child_text) or re.match(
                        r"^\s*\.{3,}\s*$", child_text
                    ):
                        xml_content.append(f"<!-- {child_text} -->")
                    else:
                        non_xml_content.append(child_text)
            if xml_content:
                new_pre = soup.new_tag("pre")
                new_pre["class"] = ["code", "language-markup"]
                new_code = soup.new_tag("code", attrs={"class": "language-markup"})
                new_code.string = "\n".join(xml_content)
                new_pre.append(new_code)
                td.clear()
                td.append(new_pre)
                for non_xml in non_xml_content:
                    new_p = soup.new_tag("p")
                    new_p.string = non_xml
                    td.append(new_p)
            print(f"TD XML content: {xml_content}")
            print(f"TD non-XML content: {non_xml_content}")

    # Удаляем вложенные <p>
    for p in soup.find_all("p"):
        nested_p = p.find("p")
        if nested_p:
            nested_p.unwrap()

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

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(images_dir):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.join("images", file))

    return html_path, zip_path, str(html_doc), html_filename, zip_filename


def save_edited_html(html_content, upload_id, html_filename):
    output_dir = os.path.join(settings.MEDIA_ROOT, "output", str(upload_id))
    html_path = os.path.join(output_dir, html_filename)

    soup = BeautifulSoup(html_content, "html.parser")
    if soup.head:
        soup.head.decompose()

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

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(str(html_doc))

    return html_path
