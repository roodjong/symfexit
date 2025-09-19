import urllib.parse

from django.conf import settings

from symfexit.theme.models import CurrentThemeVersion
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
