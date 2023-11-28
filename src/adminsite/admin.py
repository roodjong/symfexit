from functools import update_wrapper
from typing import List
from django.contrib import admin
from constance import config
from django.template.response import TemplateResponse
from django.urls.resolvers import URLResolver


class MyAdminSite(admin.AdminSite):
    def __init__(self, name: str = "admin") -> None:
        super().__init__(name)
        self.final_catch_all_view = False

    @property
    def site_header(self):
        return f"{config.SITE_TITLE} Administration"

    @property
    def site_title(self):
        return f"{config.SITE_TITLE} site admin"

    @property
    def index_title(self):
        return f"{config.SITE_TITLE} administration"

    def get_urls(self) -> List[URLResolver]:
        from django.urls import path, re_path, include
        from django.apps import apps

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

    def rebuild_theme(self, request):
        return TemplateResponse(request, "admin/rebuild_theme/change_list.html", {})


admin_site = MyAdminSite(name="symfexit_admin")


def get_admin_site():
    return admin_site
