from dataclasses import dataclass

from django.db import connection
from django.utils.translation import gettext_lazy as _


@dataclass
class ConfigField:
    default: object
    label: str
    field_type: str = ""


CONFIG_SCHEMA = {
    "SITE_TITLE": ConfigField(default="Membersite", label=_("Main title of this site")),
    "LOGO_IMAGE": ConfigField(default="", label=_("Organisation logo"), field_type="image_field"),
    "MAIN_SITE": ConfigField(
        default="https://roodjongeren.nl/", label=_("Main site of the organisation")
    ),
    "HOMEPAGE_CURRENT": ConfigField(
        default=0, label=_("Current home page (configure this on the home pages admin)")
    ),
}


class TenantConfig:
    """Attribute-style access to per-tenant config stored in Client.config JSONField.

    Reads/writes from connection.tenant.config, falling back to defaults
    defined in CONFIG_SCHEMA.
    """

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        try:
            field = CONFIG_SCHEMA[key]
        except KeyError as e:
            raise AttributeError(key) from e
        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            return field.default
        config_data = getattr(tenant, "config", None) or {}
        return config_data.get(key, field.default)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
            return
        if key not in CONFIG_SCHEMA:
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
