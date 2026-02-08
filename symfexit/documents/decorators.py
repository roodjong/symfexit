from functools import wraps
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import PermissionDenied
from django.shortcuts import resolve_url

from symfexit.documents.models import Directory, File, FileNode
from symfexit.members.models import User


def is_contact_person_of_folder(parent: FileNode | None, user: User):
    if parent is None:
        return False

    owner_wgs = []
    current_fn = parent
    if isinstance(current_fn, File):
        current_fn = current_fn.parent
    owner_wgs.append(current_fn.owner)
    while current_fn := current_fn.parent:
        owner_wgs.append(current_fn.owner)

    return User.objects.filter(contact_person_for_working_groups__in=owner_wgs, id=user.id).exists()


def user_passes_test(test_func, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """
    Decorator for views that checks that the user passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the user object and returns True if the user passes.
    """

    def decorator(view_func):
        def _redirect_to_login(request):
            path = request.build_absolute_uri()
            resolved_login_url = resolve_url(login_url or settings.LOGIN_URL)
            # If the login url is the same scheme and net location then just
            # use the path as the "next" url.
            login_scheme, login_netloc = urlsplit(resolved_login_url)[:2]
            current_scheme, current_netloc = urlsplit(path)[:2]
            if (not login_scheme or login_scheme == current_scheme) and (
                not login_netloc or login_netloc == current_netloc
            ):
                path = request.get_full_path()
            from django.contrib.auth.views import redirect_to_login  # noqa: PLC0415

            return redirect_to_login(path, resolved_login_url, redirect_field_name)

        def _view_wrapper(request, *args, **kwargs):
            test_pass = test_func(request, request.user)

            if test_pass:
                return view_func(request, *args, **kwargs)
            return _redirect_to_login(request)

        # Attributes used by LoginRequiredMiddleware.
        _view_wrapper.login_url = login_url
        _view_wrapper.redirect_field_name = redirect_field_name

        return wraps(view_func)(_view_wrapper)

    return decorator


def documents_permission_required(
    perm, directory_parameter=None, login_url=None, raise_exception=False
):
    """
    Decorator for views that checks whether a user has a particular permission
    enabled, redirecting to the log-in page if necessary.
    If the raise_exception parameter is given the PermissionDenied exception
    is raised.
    """
    if isinstance(perm, str):
        perms = (perm,)
    else:
        perms = perm

    if isinstance(directory_parameter, str):
        directory_parameters = (directory_parameter,)
    else:
        directory_parameters = directory_parameter

    def decorator(view_func):
        def check_perms(user):
            # First check if the user has the permission (even anon users).
            if user.has_perms(perms):
                return True
            # In case the 403 handler should be called raise the exception.
            if raise_exception:
                raise PermissionDenied
            # As the last resort, show the login form.
            return False

        def check_owner(request, user):
            for directory_param in directory_parameters:
                node_id = request.POST.get(directory_param)
                if not node_id:
                    return False
                fn_file = File.objects.filter(id=node_id).first()
                fn_dir = Directory.objects.filter(id=node_id).first()
                if fn_file is None and fn_dir is None:
                    return False
                if not is_contact_person_of_folder(fn_file or fn_dir, user):
                    return False
            return True

        def check(request, user):
            return check_owner(request, user) or check_perms(user)

        return user_passes_test(check, login_url=login_url)(view_func)

    return decorator
