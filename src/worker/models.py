from django.db import models
from django.utils.translation import gettext_lazy as _


class Task(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        COMPLETED = "completed", _("Completed")
        ERROR_UNKNOWN_TASK = "not_registered", _("Unknown task (not registered)")
        EXCEPTION = "exception", _("Exception")

    id = models.AutoField(_("identifier"), primary_key=True)
    name = models.CharField(_("name"), max_length=20)
    args = models.BinaryField(_("arguments"), blank=True, null=True)
    kwargs = models.BinaryField(_("keyword arguments"), blank=True, null=True)
    output = models.TextField(_("output"), blank=True, null=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status,
        default=Status.QUEUED,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    picked_up_at = models.DateTimeField(_("picked up at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.created_at} {_('(done)') if self.completed_at is not None else ''}"

    class Meta:
        verbose_name = _("task")
        verbose_name_plural = _("tasks")
        ordering = ["-created_at"]
