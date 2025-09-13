import re
from urllib.parse import urlencode
from uuid import UUID

import commonmark
import magic
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView
from django_drf_filepond.models import TemporaryUpload

from symfexit.documents.models import Directory, File, FileNode
from symfexit.members.models import User

README_REGEX = r"(?i)^(leesmij|readme)\.(md|txt)$"


def directory_url(
    parent_id: Directory | str | None,
    edit_mode=None,
    move_mode=None,
    delete_confirm=None,
    sorting=None,
):
    if isinstance(parent_id, Directory):
        parent_id = parent_id.id
    query = {}
    if edit_mode:
        query["edit"] = edit_mode
    if sorting and sorting != ("name",):
        query["sort"] = sorting
    if move_mode:
        query["move"] = move_mode
    if delete_confirm:
        query["delete_confirm"] = delete_confirm
    if not query:
        query = None
    if parent_id == "trash":
        return reverse("documents:trashcan", query=query)
    elif not parent_id:
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
    for sort in sorting:
        match sort:
            case "name":
                ci_sorting.append(Lower("name"))
            case "-name":
                ci_sorting.append(Lower("name").desc())
            case _:
                ci_sorting.append(sort)
    return tuple(ci_sorting)


def in_trash(node: FileNode | None) -> bool:
    if node is None:
        return False
    with connection.cursor() as cursor:
        # A recursive query can only be done using raw SQL in Django
        cursor.execute(
            """
            WITH RECURSIVE parents (
                id,
                trashed_at,
                parent_id
            ) AS (
                SELECT
                    id,
                    trashed_at,
                    parent_id
                FROM
                    documents_filenode
                WHERE
                    id = %s
                UNION ALL
                SELECT
                    f.id,
                    f.trashed_at,
                    f.parent_id
                FROM
                    parents AS p
                    INNER JOIN documents_filenode f ON f.id = p.parent_id
            )
            SELECT
                TRUE
            FROM
                parents WHERE trashed_at IS NOT NULL;
        """,
            [node.id],
        )
        row = cursor.fetchone()
    return row[0] if row else False


def first_nontrashed_parent(node: FileNode) -> UUID:
    with connection.cursor() as cursor:
        cursor.execute(
            """
                WITH RECURSIVE parents (
                    id,
                    trashed_at,
                    parent_id,
                    depth
                ) AS (
                    SELECT
                        id,
                        trashed_at,
                        parent_id,
                        1 AS depth
                    FROM
                        documents_filenode
                    WHERE
                        id = %s
                    UNION ALL
                    SELECT
                        f.id,
                        f.trashed_at,
                        f.parent_id,
                        p.depth + 1 AS depth
                    FROM
                        parents AS p
                        INNER JOIN documents_filenode f ON f.id = p.parent_id
                )
                SELECT
                    id
                FROM
                    parents
                WHERE
                    trashed_at IS NULL
                    AND depth > 1
                ORDER BY
                    depth ASC
                LIMIT 1;
        """,
            [node.id],
        )
        row = cursor.fetchone()
    return row[0] if row else None


# Create your views here.
class Documents(LoginRequiredMixin, TemplateView):
    template_name = "documents/documents.html"

    def get_files(self, parent, sorting):
        return File.objects.filter(parent=parent, trashed_at__isnull=True).order_by(
            *make_case_insensitive(sorting)
        )

    def get_directories(self, parent, sorting):
        return (
            Directory.objects.filter(parent=parent, trashed_at__isnull=True)
            .annotate(size=Count("children", filter=Q(children__trashed_at__isnull=True)))
            .order_by(*make_case_insensitive(sorting))
        )

    def url_base(self, **kwargs):
        return self.kwargs.get("slug", None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug", None)
        sorting, sorting_query = get_sorting(self.request)

        edit_mode = self.request.GET.get("edit", None)
        move_mode = self.request.GET.get("move", None)

        parent = Directory.objects.filter(id=slug).first()
        directories = self.get_directories(parent, sorting)
        files = list(self.get_files(parent, sorting))

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

        any_trash = FileNode.objects.filter(trashed_at__isnull=False).count() > 0
        parent_in_trash = in_trash(parent)

        context.update(
            {
                "title": _("Documents"),
                "show_breadcrumbs": True,
                "parent": parent,
                "directories": directories,
                "files": files,
                "breadcrumbs": build_breadcrumbs(Directory.objects.filter(id=slug).first()),
                "in_trash": parent_in_trash,
                "has_add_directory_permission": self.request.user.has_perm(
                    "documents.add_directory"
                ),
                "has_add_file_permission": self.request.user.has_perm("documents.add_file"),
                "has_rename_permission": self.request.user.has_perm("documents.change_file")
                and self.request.user.has_perm("documents.change_directory"),
                "has_move_permission": self.request.user.has_perm("documents.change_file")
                and self.request.user.has_perm("documents.change_directory"),
                "has_delete_permission": not parent_in_trash
                and self.request.user.has_perm("documents.delete_file")
                and self.request.user.has_perm("documents.delete_directory"),
                "show_trashcan": any_trash,
                "standard_query": sorting_query,
                "buttons_active": not (edit_mode or move_mode),
                "show_buttons": self.request.user.has_perm("documents.change_directory")
                or self.request.user.has_perm("documents.change_file")
                or self.request.user.has_perm("documents.delete_directory")
                or self.request.user.has_perm("documents.delete_file"),
                "show_trashed_at": False,
                "name_url": directory_url(
                    self.url_base(),
                    sorting=("name",) if "name" not in sorting else ("-name",),
                    move_mode=move_mode,
                ),
                "size_url": directory_url(
                    self.url_base(),
                    sorting=("-size",) if "-size" not in sorting else ("size",),
                    move_mode=move_mode,
                ),
                "created_at_url": directory_url(
                    self.url_base(),
                    sorting=("-created_at",) if "-created_at" not in sorting else ("created_at",),
                    move_mode=move_mode,
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


class Trashcan(Documents):
    def get_files(self, parent, sorting):
        return File.objects.filter(trashed_at__isnull=False).order_by(
            *make_case_insensitive(sorting)
        )

    def get_directories(self, parent, sorting):
        return (
            Directory.objects.filter(trashed_at__isnull=False)
            .annotate(size=Count("children"))
            .order_by(*make_case_insensitive(sorting))
        )

    def url_base(self, **kwargs):
        return "trash"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "title": _("Trashcan"),
                "show_breadcrumbs": False,
                "has_add_directory_permission": False,
                "has_add_file_permission": False,
                "has_rename_permission": False,
                "show_trashed_at": True,
                "show_trashcan": False,
                "readme_file": None,
            }
        )
        delete_confirm_id = self.request.GET.get("delete_confirm")
        if delete_confirm_id:
            delete_node = get_object_or_404(FileNode, id=delete_confirm_id)
            context.update(
                {"delete_confirm": delete_confirm_id, "delete_confirm_name": delete_node.name}
            )
        return context


@login_required
def file(request, slug):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    file = get_object_or_404(File, id=slug)
    _, sorting_query = get_sorting(request)
    context = {
        "file": file,
        "breadcrumbs": build_breadcrumbs(file),
        "standard_query": sorting_query,
        "in_trash": in_trash(file),
        "is_markdown": file.content_type == "text/markdown",
    }
    if is_image(file.content_type):
        return render(
            request,
            "documents/image_file.html",
            context,
        )
    if file.content_type == "application/pdf":
        return render(
            request,
            "documents/pdf_file.html",
            context,
        )
    if file.content_type in {"text/plain", "text/markdown"}:
        content = file.content.read().decode("utf-8", errors="ignore")
        if file.content_type == "text/markdown":
            content = commonmark.commonmark(content)
        return render(
            request,
            "documents/text_file.html",
            {**context, "content": content},
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


def build_breadcrumbs(node: FileNode):
    breadcrumbs = []
    while node:
        breadcrumbs.append(node)
        if node.trashed_at:
            break
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
        if in_trash(node):
            return redirect(
                directory_url(first_nontrashed_parent(node), sorting=sorting, move_mode=node_id)
            )
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
        node.trashed_at = None
        node.save()
    except IntegrityError:
        messages.add_message(
            request,
            messages.ERROR,
            _("A file or directory with the same name already exists in this location."),
        )
        return redirect(directory_url(node.parent, sorting=sorting, move_mode=node_id))
    return redirect(directory_url(newparent.id if newparent else None, sorting=sorting))


@permission_required("documents.delete_directory", raise_exception=True)
@permission_required("documents.delete_file", raise_exception=True)
def trash(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    node_id = request.POST.get("node_id")
    confirm = request.POST.get("confirm", "false")
    cancel = request.POST.get("cancel")
    sorting, sorting_query = get_sorting(request)
    node = get_object_or_404(FileNode, id=node_id)

    if node.trashed_at is None:
        node.trashed_at = timezone.now()
        node.save()
        messages.add_message(
            request, messages.INFO, _("File or directory has been moved to the trashcan.")
        )
        return redirect(directory_url(node.parent, sorting=sorting))

    if cancel:
        return redirect(directory_url("trash", sorting=sorting))

    if confirm != "true":
        return redirect(directory_url("trash", delete_confirm=node_id, sorting=sorting))
    else:
        node.delete()
        messages.add_message(request, messages.INFO, _("File or directory deleted successfully."))
        return redirect(directory_url("trash", sorting=sorting))
