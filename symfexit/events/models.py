import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import LocalGroup, User


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.TextField(_("name"))
    description = models.TextField(_("description"))
    location = models.TextField(_("location"))

    starts_at = models.DateTimeField(_("starts at"))

    ends_at = models.DateTimeField(_("ends at"))

    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
        verbose_name=_("event creator"),
    )
    organised_by = models.ForeignKey(
        LocalGroup,
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
        verbose_name=_("organized by"),
    )

    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")

    def __str__(self):
        return f"{self.name}\n{self.starts_at}-{self.starts_at}"
