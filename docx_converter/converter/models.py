import uuid

from django.db import models


class DocumentUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    docx_file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    html_file = models.FileField(upload_to="output/%Y/%m/%d/", blank=True, null=True)
    images_zip = models.FileField(upload_to="output/%Y/%m/%d/", blank=True, null=True)

    def __str__(self):
        return f"Upload {self.id}"
