from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

# from symfexit.adminsite.admin import admin_site
from symfexit.root.utils import enable_if


def health_check(request):
    return HttpResponse("OK")

def regular_urlpatterns():
    from symfexit.root.urls import urlpatterns
    return urlpatterns


urlpatterns = (
    [
        path("healthz", health_check, name="healthz"),
        path("management/", admin.site.urls),
    ]
    + enable_if(
        settings.SINGLE_SITE,
        regular_urlpatterns
    )
)
