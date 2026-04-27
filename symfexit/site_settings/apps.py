from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SiteSettingsConfig(AppConfig):
    name = "symfexit.site_settings"
    label = "site_settings"
    verbose_name = _("Settings")

    def get_app_admin_urls(self, admin_site):
        from django.urls import path  # noqa: PLC0415

        from symfexit.site_settings.views import SiteSettingsView  # noqa: PLC0415

        view = SiteSettingsView.as_view(admin_site=admin_site)
        return [path("", admin_site.admin_view(view), name="site_settings_changelist")]

    def get_admin_app_list_entry(self, request, admin_site):
        from django.urls import reverse  # noqa: PLC0415

        return {
            "name": str(self.verbose_name),
            "app_label": self.label,
            "app_url": reverse(f"{admin_site.name}:site_settings_changelist"),
            "has_module_perms": True,
            "models": [
                {
                    "name": str(_("Site settings")),
                    "object_name": "SiteSettings",
                    "admin_url": reverse(f"{admin_site.name}:site_settings_changelist"),
                    "view_only": False,
                }
            ],
        }
