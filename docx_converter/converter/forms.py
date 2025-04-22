from django import forms


class DocumentUploadForm(forms.Form):
    docx_file = forms.FileField(label="Upload .docx file")


class HtmlEditForm(forms.Form):
    html_content = forms.CharField(widget=forms.Textarea, label="Edit HTML")
