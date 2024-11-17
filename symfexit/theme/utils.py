from datetime import datetime

from django.conf import settings


def get_time_millis() -> int:
    return int(datetime.now().timestamp() * 1000)


def get_theme_filename(version: int | None):
    if not version:
        return "styles.css"
    if settings.DJANGO_ENV == "development":
        return "styles.css"
    return f"styles-{version}.css"
