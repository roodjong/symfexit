from datetime import datetime
from django.db import models

from django.utils.translation import gettext_lazy as _

from theme.utils import get_time_millis

class TailwindKey(models.Model):
    COLOR_KEY_CHOICES = [
        ("primary", "Primary Color"),
        ("secondary", "Secondary Color"),
    ]
    id = models.AutoField(primary_key=True)
    name = models.CharField(_("name"), unique=True, max_length=20, choices=COLOR_KEY_CHOICES)
    value = models.TextField(_("value"))

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"

class CurrentThemeVersion(models.Model):
    id = models.AutoField(primary_key=True)
    version = models.BigIntegerField(_("version"), unique=True, default=get_time_millis)

    class Meta:
        get_latest_by = "version"

    def __str__(self) -> str:
        return self.version
