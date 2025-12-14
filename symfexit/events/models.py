from django.db import models
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import User


class Event(models.Model):
    event_name = models.CharField(_("name"))
    event_organiser = models.CharField(_("organiser"))
    event_date = models.DateTimeField(_("start date"))
    event_end = models.DateTimeField(_("end date"), blank=True, null=True)
    event_desc = models.TextField(_("description"))
    attendees = models.ManyToManyField(
        User,
        related_name="signed_up_events",
        blank=True,
        verbose_name=_("attendees"),
        editable=False,
    )

    class Meta:
        verbose_name = _("event")
        verbose_name_plural = _("events")

    def __str__(self):
        return f"{self.event_name}"
