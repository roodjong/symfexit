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
from django.urls import include, path, reverse
from django.views.generic import RedirectView

from adminsite.admin import admin_site
from symfexit.settings import DOCS_ENABLED, HOME_ENABLED, SIGNUP_ENABLED
from symfexit.utils import enable_if

try:
    import django_browser_reload

    django_browser_reload_enabled = True
except ImportError:
    django_browser_reload_enabled = False

urlpatterns = (
    [path("tinymce/", include("tinymce.urls"))]
    + enable_if(
        HOME_ENABLED,
        lambda: [path("", include("home.urls"))],
        otherwise=lambda: [
            path(
                "",
                RedirectView.as_view(pattern_name="members:memberdata"),
                name="index",
            )
        ],
    )
    + [
        path("", include("members.urls")),
    ]
    + enable_if(DOCS_ENABLED, lambda: [path("", include("documents.urls"))])
    + enable_if(SIGNUP_ENABLED, lambda: [path("", include("signup.urls"))])
    + enable_if(
        settings.MOLLIE_API_KEY,
        lambda: [path("mollie/", include("payments_mollie.urls"))],
    )
    + enable_if(
        settings.DEBUG,
        lambda: [path("dummy/", include("payments_dummy.urls"))],
    )
    + [
        path("admin/", admin_site.urls),
        path("accounts/", include("django.contrib.auth.urls")),
    ]
    + enable_if(
        django_browser_reload_enabled,
        lambda: [path("__reload__/", include("django_browser_reload.urls"))],
    )
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
)
