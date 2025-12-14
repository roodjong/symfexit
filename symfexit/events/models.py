from django.db import models
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import User

# Create your models here.


class Event(models.Model):
    event_name = models.CharField(_("event name"))
    event_organiser = models.CharField(_("event organiser"))
    event_date = models.DateTimeField(_("event date"))
    event_desc = models.TextField(_("event description"))
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
