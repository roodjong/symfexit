from django.conf import settings
from django.db import connection


class TenantConfig:
    """Attribute-style access to per-tenant config stored in Client.config JSONField.

    Reads/writes from connection.tenant.config, falling back to defaults
    defined in settings.CONSTANCE_CONFIG.
    """

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        try:
            meta = settings.CONSTANCE_CONFIG[key]
        except KeyError as e:
            raise AttributeError(key) from e
        default = meta[0]
        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            return default
        config_data = getattr(tenant, "config", None) or {}
        return config_data.get(key, default)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
            return
        if key not in settings.CONSTANCE_CONFIG:
            raise AttributeError(key)
        tenant = getattr(connection, "tenant", None)
        if tenant is None or not hasattr(tenant, "config"):
            raise RuntimeError("No tenant set on connection; cannot write config")
        if tenant.config is None:
            tenant.config = {}
        tenant.config[key] = value
        from symfexit.tenants.models import Client  # noqa: PLC0415

        Client.objects.filter(pk=tenant.pk).update(config=tenant.config)


config = TenantConfig()
