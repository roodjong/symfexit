import urllib.parse

from django.conf import settings
from django.templatetags.static import static
from tailwind import get_config

from symfexit.theme.models import CurrentThemeVersion
from symfexit.theme.utils import get_theme_filename


def is_path_absolute(path):
    return path.startswith("/") or path.startswith("http")


def current_theme(request):
    try:
        version = CurrentThemeVersion.objects.latest().version
    except CurrentThemeVersion.DoesNotExist:
        version = None
    is_static_path = not is_path_absolute(get_config("TAILWIND_CSS_PATH"))
    if is_static_path:
        builtin_css = static(get_config("TAILWIND_CSS_PATH"))
    else:
        builtin_css = get_config("TAILWIND_CSS_PATH")
    if not version:
        return {
            "current_theme_css_file": builtin_css,
        }
    return {
        "current_theme_css_file": "/"
        + urllib.parse.urljoin(settings.DYNAMIC_THEME_URL, get_theme_filename(version)),
    }
