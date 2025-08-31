import re
from urllib.parse import urlencode
from uuid import UUID

import commonmark
import magic
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from django_drf_filepond.models import TemporaryUpload

from symfexit.documents.models import Directory, File, FileNode
from symfexit.members.models import User

README_REGEX = r"(?i)^(leesmij|readme)\.(md|txt)$"


def directory_url(parent_id: Directory | str | None, edit_mode=None, move_mode=None, sorting=None):
    if isinstance(parent_id, Directory):
        parent_id = parent_id.id
    query = {}
    if edit_mode:
        query["edit"] = edit_mode
    if sorting and sorting != ("name",):
        query["sort"] = sorting
    if move_mode:
        query["move"] = move_mode
    if not query:
        query = None
    if not parent_id:
        return reverse("documents:documents", query=query)
    else:
        return reverse("documents:documents", kwargs={"slug": parent_id}, query=query)


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


def make_case_insensitive(sorting):
    ci_sorting = []
    for s in sorting:
        if "name" in s:
            ci_sorting.append(Lower(s))
        else:
            ci_sorting.append(s)
    return tuple(ci_sorting)


# Create your views here.
class Documents(LoginRequiredMixin, TemplateView):
    template_name = "documents/documents.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug", None)
        sorting, sorting_query = get_sorting(self.request)

        edit_mode = self.request.GET.get("edit", None)
        move_mode = self.request.GET.get("move", None)

        parent = Directory.objects.filter(id=slug).first()
        directories = (
            Directory.objects.filter(parent=slug)
            .annotate(size=Count("children"))
            .order_by(*make_case_insensitive(sorting))
        )
        files = list(File.objects.filter(parent=slug).order_by(*make_case_insensitive(sorting)))

        # Search for a LEESMIJ.md, LEESMIJ.txt, README.md or README.txt file (case insensitive) in that order
        def sort_key(f):
            s = f.name.lower().rsplit(".", 1)
            # Just conincidentally l is before r and m is before t
            return s[0][0], s[1][0]

        readme_files = sorted(
            filter(
                lambda f: re.match(README_REGEX, f.name),
                files,
            ),
            key=sort_key,
        )
        if readme_files:
            context["readme_file"] = readme_files[0]
            context["readme_rendered"] = commonmark.commonmark(
                readme_files[0].content.read().decode()
            )

        context.update(
            {
                "parent": parent,
                "directories": directories,
                "files": files,
                "breadcrumbs": build_breadcrumbs(Directory.objects.filter(id=slug).first()),
                "has_add_directory_permission": self.request.user.has_perm(
                    "documents.add_directory"
                ),
                "has_add_file_permission": self.request.user.has_perm("documents.add_file"),
                "has_change_file_permission": self.request.user.has_perm("documents.change_file"),
                "has_change_directory_permission": self.request.user.has_perm(
                    "documents.change_directory"
                ),
                "standard_query": sorting_query,
                "buttons_active": not (edit_mode or move_mode),
                "show_buttons": self.request.user.has_perm("documents.change_directory")
                or self.request.user.has_perm("documents.change_file")
                or self.request.user.has_perm("documents.delete_directory")
                or self.request.user.has_perm("documents.delete_file"),
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
        if edit_mode:
            edit_node = get_object_or_404(FileNode, id=edit_mode)
            context.update(
                {
                    "edit_mode": edit_mode,
                    "edit_old_full_name": edit_node.name,
                    "edit_old_name": edit_node.name.rsplit(".", 1)[0],
                    "edit_old_ext": edit_node.name.rsplit(".", 1)[-1]
                    if "." in edit_node.name
                    else "",
                }
            )
        if move_mode:
            move_node = get_object_or_404(FileNode, id=move_mode)

            parents = []
            if parent is not None:
                current_dir = parent
                parents.append(current_dir.id)
                while current_dir := current_dir.parent:
                    parents.append(current_dir.id)
            if move_node.id in parents:
                messages.add_message(
                    self.request,
                    messages.ERROR,
                    _("You cannot move a directory into itself or one of its subdirectories."),
                )

            move_query = {"move": move_mode}
            if sorting_query:
                move_query["sort"] = sorting
            standard_query = "?" + urlencode(move_query, doseq=True)
            context.update(
                {
                    "standard_query": standard_query,
                    "valid_move": move_node.id not in parents,
                    "move_mode": UUID(move_mode),
                    "move_node_name": move_node.name,
                    "move_node_old_parent": move_node.parent.id if move_node.parent else None,
                }
            )
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.member_type != User.MemberType.MEMBER:
            return redirect("members:memberdata")

        sorting, sorting_query = get_sorting(request)
        if request.GET.get("edit") and not (
            request.user.has_perm("documents.change_file")
            and request.user.has_perm("documents.change_directory")
        ):
            return redirect(directory_url(self.kwargs.get("slug", None), sorting=sorting))
        if request.GET.get("move") and not (
            request.user.has_perm("documents.change_file")
            and request.user.has_perm("documents.change_directory")
        ):
            return redirect(directory_url(self.kwargs.get("slug", None), sorting=sorting))
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
            {"file": file, "breadcrumbs": build_breadcrumbs(file), "standard_query": sorting_query},
        )
    if file.content_type == "application/pdf":
        return render(
            request,
            "documents/pdf_file.html",
            {"file": file, "breadcrumbs": build_breadcrumbs(file), "standard_query": sorting_query},
        )
    if file.content_type in {"text/plain", "text/markdown"}:
        content = file.content.read().decode("utf-8", errors="ignore")
        if file.content_type == "text/markdown":
            content = commonmark.commonmark(content)
        return render(
            request,
            "documents/text_file.html",
            {
                "file": file,
                "content": content,
                "is_markdown": file.content_type == "text/markdown",
                "breadcrumbs": build_breadcrumbs(file),
                "standard_query": sorting_query,
            },
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
    if parent_id:
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
        if mimetype == "text/plain" and tmpfile.upload_name.lower().endswith(".md"):
            mimetype = "text/markdown"
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
        if mimetype == "text/plain" and tmpfile.upload_name.lower().endswith(".md"):
            mimetype = "text/markdown"
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


@permission_required("documents.change_directory", raise_exception=True)
@permission_required("documents.change_file", raise_exception=True)
def edit(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    node_id = request.POST.get("node_id")
    parent_id = request.POST.get("parent_id")
    newname = request.POST.get("newname", "")
    newext = request.POST.get("newext", "")
    sorting, sorting_query = get_sorting(request)

    if not newname.strip():
        return redirect(directory_url(parent_id, sorting=sorting, edit_mode=node_id))

    node = get_object_or_404(FileNode, id=node_id)

    try:
        node.name = newname + (f".{newext}" if newext else "")
        node.save()
    except IntegrityError:
        messages.add_message(
            request,
            messages.ERROR,
            _("A file or directory with the same name already exists in this location."),
        )
        return redirect(directory_url(node.parent.id if node.parent else None, sorting=sorting))
    return redirect(directory_url(node.parent.id if node.parent else None, sorting=sorting))


@permission_required("documents.change_directory", raise_exception=True)
@permission_required("documents.change_file", raise_exception=True)
def move(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    node_id = request.POST.get("node_id")
    newparent_id = request.POST.get("newparent_id")
    action = request.POST.get("action")
    sorting, sorting_query = get_sorting(request)

    node = get_object_or_404(FileNode, id=node_id)
    if action == "cancel":
        return redirect(directory_url(node.parent, sorting=sorting))

    if not newparent_id:
        # Not confirmed the move yet
        return redirect(directory_url(node.parent, sorting=sorting, move_mode=node_id))

    newparent = None
    if newparent_id != "toplevel":
        newparent = get_object_or_404(Directory, id=newparent_id)

    if node.id == newparent_id:
        messages.add_message(
            request,
            messages.ERROR,
            _("You cannot move a directory into itself."),
        )
        return redirect(directory_url(node.parent, sorting=sorting, move_mode=node_id))

    try:
        node.parent = newparent
        node.save()
    except IntegrityError:
        messages.add_message(
            request,
            messages.ERROR,
            _("A file or directory with the same name already exists in this location."),
        )
        return redirect(directory_url(node.parent, sorting=sorting, move_mode=node_id))
    return redirect(directory_url(newparent.id if newparent else None, sorting=sorting))
