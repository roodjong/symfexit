from django.apps import AppConfig


class ThemeConfig(AppConfig):
    name = "theme"

    def get_app_admin_urls(self, admin_site):
        from django.urls import path

        from theme.admin import RebuildTheme

        rebuild_theme = RebuildTheme.as_view(admin_site=admin_site)
        return [
            path("rebuild/", admin_site.admin_view(rebuild_theme), name="rebuild_theme")
        ]
