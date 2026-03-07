from functools import update_wrapper

from django.contrib import admin
from django.urls.resolvers import URLResolver
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from symfexit.tenants.models import Client


class TenantAdminSite(admin.AdminSite):
    def __init__(self, name: str = "admin") -> None:
        super().__init__(name)
        self.final_catch_all_view = False

    @property
    def site_header(self):
        tenant = self.get_active_tenant()
        site_title = tenant.site_title if tenant else "Membersite"
        return format_lazy(_("{site_title} Administration"), site_title=site_title)

    @property
    def site_title(self):
        tenant = self.get_active_tenant()
        site_title = tenant.site_title if tenant else "Membersite"
        return format_lazy(_("{site_title} site admin"), site_title=site_title)

    @property
    def index_title(self):
        tenant = self.get_active_tenant()
        site_title = tenant.site_title if tenant else "Membersite"
        return format_lazy(_("{site_title} administration"), site_title=site_title)

    def get_active_tenant(self):
        # Try to get tenant from request if available
        import threading

        request = getattr(threading.local(), "request", None)
        if request and hasattr(request, "tenant"):
            return request.tenant
        # Fallback: get first tenant
        return Client.objects.first()

    def get_urls(self) -> list[URLResolver]:
        from django.apps import apps  # noqa: PLC0415
        from django.urls import include, path, re_path  # noqa: PLC0415

        def wrap(view, cacheable=False):
            def wrapper(*args, **kwargs):
                return self.admin_view(view, cacheable)(*args, **kwargs)

            wrapper.admin_site = self
            return update_wrapper(wrapper, view)

        urls = super().get_urls()
        for app in apps.get_app_configs():
            if hasattr(app, "get_app_admin_urls"):
                urls += [path(f"{app.label}/", include(app.get_app_admin_urls(self)))]
        urls += [
            re_path(r"(?P<url>.*)$", wrap(self.catch_all_view)),
        ]
        return urls


admin_site = TenantAdminSite(name="symfexit_admin")


def get_admin_site():
    return admin_site
