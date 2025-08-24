import django
from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate


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

    def ready(self):
        post_migrate.connect(ensure_single_tenant_if_enabled, sender=self)
