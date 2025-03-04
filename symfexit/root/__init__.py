# Minimal Django templates engine to render the error templates
# regardless of the project's TEMPLATES setting. Templates are
# read directly from the filesystem so that the error handler
# works even if the template loader is broken.
from pathlib import Path
import types
from django.conf import settings
from django.http import Http404, HttpResponseNotFound
from django.template import Context, Engine
from django.urls import resolve
from django.views import debug


DEBUG_ENGINE = Engine(
    debug=True,
    libraries={"i18n": "django.templatetags.i18n"},
)

def builtin_template_path(name):
    """
    Return a path to a builtin template.

    Avoid calling this function at the module level or in a class-definition
    because __file__ may not exist, e.g. in frozen environments.
    """
    return Path(__file__).parent / "templates" / name

def get_caller(request):
    resolver_match = request.resolver_match
    if resolver_match is None:
        try:
            resolver_match = resolve(request.path)
        except Http404:
            pass
    return "" if resolver_match is None else resolver_match._func_path

def custom_404_response(request, exception):
    """Create a technical 404 error response. `exception` is the Http404."""
    try:
        error_url = exception.args[0]["path"]
    except (IndexError, TypeError, KeyError):
        error_url = request.path_info[1:]  # Trim leading slash

    try:
        tried = exception.args[0]["tried"]
    except (IndexError, TypeError, KeyError):
        resolved = True
        tried = request.resolver_match.tried if request.resolver_match else None
    else:
        resolved = False
        if not tried or (  # empty URLconf
            request.path_info == "/"
            and len(tried) == 1
            and len(tried[0]) == 1  # default URLconf
            and getattr(tried[0][0], "app_name", "")
            == getattr(tried[0][0], "namespace", "")
            == "admin"
        ):
            return debug.default_urlconf(request)

    urlconf = getattr(request, "urlconf", settings.ROOT_URLCONF)
    if isinstance(urlconf, types.ModuleType):
        urlconf = urlconf.__name__

    with builtin_template_path("technical_404.html").open(encoding="utf-8") as fh:
        t = DEBUG_ENGINE.from_string(fh.read())
    reporter_filter = debug.get_default_exception_reporter_filter()
    c = Context(
        {
            "urlconf": urlconf,
            "root_urlconf": settings.ROOT_URLCONF,
            "request_path": error_url,
            "urlpatterns": tried,
            "resolved": resolved,
            "reason": str(exception),
            "request": request,
            "settings": reporter_filter.get_safe_settings(),
            "raising_view_name": get_caller(request),
            "hostname": request.get_host().split(":")[0],
            "tenant_not_found": 'No tenant for hostname' in str(exception)
        }
    )
    return HttpResponseNotFound(t.render(c))

debug.technical_404_response = custom_404_response
