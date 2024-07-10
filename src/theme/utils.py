from datetime import datetime
from typing import Optional

from django.conf import settings


def get_theme_filename(version: Optional[datetime]):
    if not version:
        return "styles.css"
    if settings.DJANGO_ENV == "development":
        return "styles.css"
    return f"styles-{version.timestamp()}.css"
