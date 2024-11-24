from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class ThemeConfig(AppConfig):
    name = "symfexit.theme"
    verbose_name = _("Theme")

    def get_app_admin_urls(self, admin_site):
        from django.urls import path

        from symfexit.theme.admin import RebuildTheme

        rebuild_theme = RebuildTheme.as_view(admin_site=admin_site)
        return [path("rebuild/", admin_site.admin_view(rebuild_theme), name="rebuild_theme")]
