from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

# from symfexit.adminsite.admin import admin_site
from symfexit.root.utils import enable_if

try:
    import django_browser_reload  # noqa

    django_browser_reload_enabled = True
except ImportError:
    django_browser_reload_enabled = False


def health_check(request):
    return HttpResponse("OK")


def regular_urlpatterns():
    from symfexit.root.urls import urlpatterns  # noqa: PLC0415

    return urlpatterns


urlpatterns = (
    [
        path("healthz", health_check, name="healthz"),
        path("management/", admin.site.urls),
    ]
    + enable_if(
        django_browser_reload_enabled,
        lambda: [path("__reload__/", include("django_browser_reload.urls"))],
    )
    + enable_if(settings.SINGLE_SITE, regular_urlpatterns)
)
