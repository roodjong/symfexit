from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ThemeConfig(AppConfig):
    name = "symfexit.theme"
    verbose_name = _("Theme")

    def get_app_admin_urls(self, admin_site):
        from django.urls import path  # noqa: PLC0415

        from symfexit.theme.admin import RebuildTheme  # noqa: PLC0415

        rebuild_theme = RebuildTheme.as_view(admin_site=admin_site)
        return [path("rebuild/", admin_site.admin_view(rebuild_theme), name="rebuild_theme")]
