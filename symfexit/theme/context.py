import urllib.parse

from django.conf import settings

from symfexit.theme.models import CurrentThemeVersion, TailwindKey
from symfexit.theme.utils import get_theme_filename


def is_path_absolute(path):
    return path.startswith("/") or path.startswith("http")


def current_theme(request):
    try:
        version = CurrentThemeVersion.objects.latest().version
    except CurrentThemeVersion.DoesNotExist:
        version = None
    return {
        "current_theme_css_file": "/"
        + urllib.parse.urljoin(
            settings.DYNAMIC_THEME_URL, get_theme_filename(request.tenant, version)
        ),
    }


def theme_vars(request):
    vars = {}
    for item in TailwindKey.objects.all():
        vars[item.name.replace("-", "_")] = item.value
    return {"theme": vars}
