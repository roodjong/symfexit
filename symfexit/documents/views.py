from urllib.parse import urlencode

import magic
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from django_drf_filepond.models import TemporaryUpload

from symfexit.documents.models import Directory, File
from symfexit.members.models import User


def directory_url(parent_id):
    if not parent_id:
        return reverse("documents:documents")
    else:
        return reverse("documents:documents", kwargs={"slug": parent_id})


def get_sorting(request):
    sorting = request.GET.getlist("sort")
    if not sorting:
        sorting = ("name",)
    sorting = tuple(
        filter(lambda s: s.removeprefix("-") in ("name", "created_at", "size"), sorting)
    )
    sorting_query = ""
    if sorting != ("name",):
        sorting_query = "?" + urlencode({"sort": sorting}, doseq=True)
    return sorting, sorting_query


# Create your views here.
class Documents(LoginRequiredMixin, TemplateView):
    template_name = "documents/documents.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug", None)
        sorting, sorting_query = get_sorting(self.request)
        directories = (
            Directory.objects.filter(parent=slug)
            .annotate(size=Count("children"))
            .order_by(*sorting)
        )
        context.update(
            {
                "parent": Directory.objects.filter(id=slug).first(),
                "directories": directories,
                "files": File.objects.filter(parent=slug).order_by(*sorting),
                "breadcrumbs": build_breadcrumbs(Directory.objects.filter(id=slug).first()),
                "has_add_directory_permission": self.request.user.has_perm(
                    "documents.add_directory"
                ),
                "has_add_file_permission": self.request.user.has_perm("documents.add_file"),
                "sorting_query": sorting_query,
                "name_url": reverse(
                    "documents:documents",
                    kwargs={"slug": slug} if slug else None,
                    query={"sort": "{}name".format("-" if "name" in sorting else "")}
                    if sorting == ("name",)
                    else None,
                ),
                "size_url": reverse(
                    "documents:documents",
                    kwargs={"slug": slug} if slug else None,
                    query={"sort": "{}size".format("" if "-size" in sorting else "-")},
                ),
                "created_at_url": reverse(
                    "documents:documents",
                    kwargs={"slug": slug} if slug else None,
                    query={"sort": "{}created_at".format("" if "-created_at" in sorting else "-")},
                ),
            }
        )
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.member_type != User.MemberType.MEMBER:
            return redirect("members:memberdata")
        return super().dispatch(request, args, kwargs)


@login_required
def file(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    _, sorting_query = get_sorting(request)
    if is_image(file.content_type):
        return render(
            request,
            "documents/image_file.html",
            {"file": file, "breadcrumbs": build_breadcrumbs(file), "sorting_query": sorting_query},
        )
    if file.content_type == "application/pdf":
        return render(
            request,
            "documents/pdf_file.html",
            {"file": file, "breadcrumbs": build_breadcrumbs(file), "sorting_query": sorting_query},
        )
    response = HttpResponse(file.content, content_type=file.content_type)
    response["Content-Disposition"] = f"attachment; filename={file.name}"
    return response


@xframe_options_exempt
@login_required
def file_pdf(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    if file.content_type != "application/pdf":
        return HttpResponseNotAllowed(["GET"])
    response = HttpResponse(file.content, content_type=file.content_type)
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@login_required
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


@permission_required("documents.add_directory", raise_exception=True)
def new_directory(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    name = request.POST.get("name")
    parent_id = request.POST.get("parent_id")
    parent = None
    if parent_id and parent_id != "null":
        parent = get_object_or_404(Directory, id=parent_id)
    try:
        directory = Directory.objects.create(name=name, parent=parent)
    except IntegrityError:
        messages.add_message(
            request,
            messages.ERROR,
            _("A file or directory with the same name already exists in this location."),
        )
        return redirect(directory_url(parent_id))
    return redirect(directory_url(directory.id))


@permission_required("documents.add_file", raise_exception=True)
def upload_files(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    fp_files = request.POST.getlist("filepond")
    parent_id = request.POST.get("parent_id")
    if (not fp_files or len(fp_files) == 1 and fp_files[0] == "") and request.FILES.get(
        "filepond"
    ) is None:
        return redirect(directory_url(parent_id))
    parent = None
    if parent_id:
        parent = get_object_or_404(Directory, id=parent_id)
    failed_files = []
    for f in fp_files:
        tmpfile = get_object_or_404(TemporaryUpload, upload_id=f)
        mimetype = magic.from_file(tmpfile.file.path, mime=True)
        try:
            with transaction.atomic():
                file = File.objects.create(
                    name=tmpfile.upload_name,
                    size=tmpfile.file.size,
                    content_type=mimetype,
                    parent=parent,
                )
                with open(tmpfile.file.path, "rb") as file_content:
                    file.content.save(tmpfile.upload_name, file_content)
        except IntegrityError:
            failed_files.append(tmpfile.upload_name)
        finally:
            tmpfile.delete()
    for f in request.FILES.getlist("filepond"):
        mimetype = magic.from_buffer(f.read(2048), mime=True)
        f.seek(0)
        try:
            with transaction.atomic():
                file = File.objects.create(
                    name=f.name,
                    size=f.size,
                    content_type=mimetype,
                    parent=parent,
                )
                file.content.save(f.name, f)
        except IntegrityError:
            failed_files.append(f.name)
    if failed_files:
        messages.add_message(
            request,
            messages.ERROR,
            _(
                "The following files could not be uploaded because a file or directory with the same name already exists in this location: "
            )
            + ", ".join(failed_files),
        )
    return redirect(directory_url(parent_id))
