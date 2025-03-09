from datetime import datetime

from django.conf import settings

from symfexit.tenants.models import Client


def get_time_millis() -> int:
    return int(datetime.now().timestamp() * 1000)


def get_theme_filename(tenant: Client, version: int | None):
    if not version:
        return f"styles-{tenant.schema_name}.css"
    if settings.SYMFEXIT_ENV == "development":
        return f"styles-{tenant.schema_name}.css"
    return f"styles-{tenant.schema_name}-{version}.css"
