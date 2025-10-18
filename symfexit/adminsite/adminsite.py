from functools import update_wrapper

from constance import config
from django.contrib import admin
from django.urls.resolvers import URLResolver
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _


class MyAdminSite(admin.AdminSite):
    def __init__(self, name: str = "admin") -> None:
        super().__init__(name)
        self.final_catch_all_view = False

    @property
    def site_header(self):
        # Text to put in each page's <div id="site-name">.
        return format_lazy(_("{site_title} Administration"), site_title=config.SITE_TITLE)

    @property
    def site_title(self):
        # Text to put at the end of each page's <title>.
        return format_lazy(_("{site_title} site admin"), site_title=config.SITE_TITLE)

    @property
    def index_title(self):
        # Text to put at the top of the admin index page.
        return format_lazy(_("{site_title} administration"), site_title=config.SITE_TITLE)

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


admin_site = MyAdminSite(name="symfexit_admin")


def get_admin_site():
    return admin_site
