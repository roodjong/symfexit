import django
from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def create_dev_domains(client):
    from symfexit.tenants.models import Domain  # noqa: PLC0415

    try:
        Domain.objects.create(domain="127.0.0.1", tenant=client, is_primary=False)
    except django.db.utils.IntegrityError:
        pass

    try:
        Domain.objects.create(domain="localhost", tenant=client, is_primary=False)
    except django.db.utils.IntegrityError:
        pass


def ensure_single_tenant_if_enabled(sender, **kwargs):
    from symfexit.tenants.models import Client, Domain  # noqa: PLC0415

    if settings.SINGLE_SITE:
        (client, _) = Client.objects.get_or_create(
            schema_name="public", defaults={"name": "Symfexit"}
        )
        Domain.objects.get_or_create(
            defaults={"is_primary": True}, domain=settings.SINGLE_SITE_DOMAIN, tenant=client
        )
        if settings.SYMFEXIT_ENV == "development":
            create_dev_domains(client)


class TenantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.tenants"
    verbose_name = _("Tenants")

    def ready(self):
        post_migrate.connect(ensure_single_tenant_if_enabled, sender=self)


class SiteSettingsConfig(AppConfig):
    name = "symfexit.site_settings"
    label = "site_settings"
    verbose_name = _("Settings")

    def get_app_admin_urls(self, admin_site):
        from django.urls import path  # noqa: PLC0415

        from symfexit.tenants.admin import SiteSettingsView  # noqa: PLC0415

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
