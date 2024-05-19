from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView

from documents.models import Directory, File


# Create your views here.
class Documents(LoginRequiredMixin, TemplateView):
    template_name = "documents/documents.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug", None)
        context["parent"] = Directory.objects.filter(id=slug).first()
        context["directories"] = Directory.objects.filter(parent=slug)
        context["files"] = File.objects.filter(parent=slug)
        context["breadcrumbs"] = build_breadcrumbs(context["parent"])
        return context


def file(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    if is_image(file.content_type):
        return render(
            request,
            "documents/image_file.html",
            {"file": file, "breadcrumbs": build_breadcrumbs(file)},
        )
    if file.content_type == "application/pdf":
        return render(
            request,
            "documents/pdf_file.html",
            {"file": file, "breadcrumbs": build_breadcrumbs(file)},
        )
    response = HttpResponse(file.content, content_type=file.content_type)
    response["Content-Disposition"] = f"attachment; filename={file.name}"
    return response


@xframe_options_exempt
def file_pdf(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    if file.content_type != "application/pdf":
        return HttpResponseNotAllowed(["GET"])
    response = HttpResponse(file.content, content_type=file.content_type)
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def file_download(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    response = HttpResponse(file.content, content_type=file.content_type)
    response["Content-Disposition"] = f"attachment; filename={file.name}"
    return response


def build_breadcrumbs(node):
    breadcrumbs = []
    while node:
        breadcrumbs.append(node)
        node = node.parent
    return reversed(breadcrumbs)


def is_image(content_type):
    return content_type.startswith("image/")
