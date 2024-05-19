from django.apps import AppConfig
from django.conf import settings


class ThemeConfig(AppConfig):
    name = "theme"

    def get_app_admin_urls(self, admin_site):
        from django.urls import path

        from theme.admin import RebuildTheme

        if not settings.THEMING_ENABLED:
            return []

        rebuild_theme = RebuildTheme.as_view(admin_site=admin_site)
        return [
            path("rebuild/", admin_site.admin_view(rebuild_theme), name="rebuild_theme")
        ]
