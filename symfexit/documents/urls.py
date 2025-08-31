from django.urls import path

from symfexit.documents.views import (
    Documents,
    edit,
    file,
    file_download,
    file_pdf,
    move,
    new_directory,
    upload_files,
)

app_name = "documents"

urlpatterns = [
    path("documenten/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/view", file, name="file"),
    path("documenten/<uuid:slug>/view-pdf", file_pdf, name="view-pdf"),
    path("documenten/<uuid:slug>/download", file_download, name="download"),
    path("documenten/create-directory", new_directory, name="create-directory"),
    path("documenten/upload", upload_files, name="upload"),
    path("documenten/edit", edit, name="edit"),
    path("documenten/move", move, name="move"),
]
