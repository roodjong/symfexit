from django.urls import path

from symfexit.documents.views import (
    Documents,
    Trashcan,
    edit,
    file,
    file_download,
    file_pdf,
    move,
    new_directory,
    trash,
    upload_files,
)

app_name = "documents"

urlpatterns = [
    path("documenten/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/view", file, name="file"),
    path("documenten/<uuid:slug>/view-pdf", file_pdf, name="view-pdf"),
    path("documenten/<uuid:slug>/download", file_download, name="download"),
    path("documenten/trashcan", Trashcan.as_view(), name="trashcan"),
    path("documenten/create-directory", new_directory, name="create-directory"),
    path("documenten/upload", upload_files, name="upload"),
    path("documenten/edit", edit, name="edit"),
    path("documenten/move", move, name="move"),
    path("documenten/trash", trash, name="trash"),
]
