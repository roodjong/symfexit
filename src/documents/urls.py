from django.urls import path

from documents.views import Documents, file, file_download, file_pdf


app_name = "documents"

urlpatterns = [
    path("documenten/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/", Documents.as_view(), name="documents"),
    path("documenten/<uuid:slug>/view/", file, name="file"),
    path("documenten/<uuid:slug>/view-pdf/", file_pdf, name="view-pdf"),
    path("documenten/<uuid:slug>/download/", file_download, name="download"),
]
