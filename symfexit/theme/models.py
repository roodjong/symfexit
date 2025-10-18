from django.db import models
from django.utils.translation import gettext_lazy as _

from symfexit.theme.utils import get_time_millis


class TailwindKey(models.Model):
    COLOR_KEY_CHOICES = [
        ("admin-color", "Admin Color"),
        ("admin-color-headerbar", "Admin Header Bar Color"),
        ("color-primary", "Primary Color"),
        ("font-header", "Font used in the header"),
    ]
    id = models.AutoField(primary_key=True)
    name = models.CharField(
        _("name"), unique=True, blank=False, max_length=80, choices=COLOR_KEY_CHOICES
    )
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
