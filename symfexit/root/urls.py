"""symfexit URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

# from symfexit.adminsite.admin import admin_site
from symfexit.root.utils import enable_if
from symfexit.root.views import CustomPasswordResetView

try:
    import django_browser_reload  # noqa

    django_browser_reload_enabled = True
except ImportError:
    django_browser_reload_enabled = False


def health_check(request):
    return HttpResponse("OK")


def chrome_devtools(request):
    """Serve devtools information that chrome can pick up
    See: https://developer.chrome.com/docs/devtools/workspaces#generate-json
    """
    import json  # noqa: PLC0415

    return HttpResponse(
        json.dumps(
            {
                "workspace": {
                    "root": str(settings.BASE_DIR),
                    "uuid": "df35bb4f-c867-471b-9767-c3c3018bbbf1",
                }
            }
        ),
        content_type="application/json",
    )


urlpatterns = (
    [
        path("healthz", health_check, name="healthz"),
        path("tinymce/", include("tinymce.urls")),
        path("", include("symfexit.home.urls")),
        path("", include("symfexit.members.urls")),
        path("", include("symfexit.documents.urls")),
        path("", include("symfexit.signup.urls")),
        path("mollie/", include("symfexit.payments.mollie.urls")),
        path("admin/", admin.site.urls),
        path("accounts/", include("django.contrib.auth.urls")),
        path("fp/", include("django_drf_filepond.urls")),
    ]
    + enable_if(
        django_browser_reload_enabled,
        lambda: [path("__reload__/", include("django_browser_reload.urls"))],
    )
    + enable_if(
        settings.DEBUG,
        lambda: [
            path("dummy/", include("symfexit.payments.dummy.urls")),
            path(".well-known/appspecific/com.chrome.devtools.json", chrome_devtools),
        ]
        + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    )
)

# Prepend the custom view to override the default password_reset URL
urlpatterns = [
    path("accounts/password_reset/", CustomPasswordResetView.as_view(), name="password_reset"),
] + list(urlpatterns)  # keep the rest of the original list intact
