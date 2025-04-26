import os
import uuid

from django.db import models


class DocumentUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    docx_file = models.FileField(upload_to="uploads/%Y/%m/%d/", max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    html_file = models.FileField(
        upload_to="output/%Y/%m/%d/", blank=True, null=True, max_length=255
    )
    images_zip = models.FileField(
        upload_to="output/%Y/%m/%d/", blank=True, null=True, max_length=255
    )

    def __str__(self):
        return f"Upload {self.id}"

    def is_valid(self):
        return all(
            [
                self.html_file and os.path.exists(self.html_file.path),
                self.images_zip and os.path.exists(self.images_zip.path),
                self.docx_file and os.path.exists(self.docx_file.path),
            ]
        )
