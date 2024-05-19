from django.db import models
from django.utils.translation import gettext_lazy as _


class Task(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        COMPLETED = "completed", _("Completed")
        ERROR_UNKNOWN_TASK = "not_registered", _("Unknown task (not registered)")
        EXCEPTION = "exception", _("Exception")

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=20)
    args = models.BinaryField(blank=True, null=True)
    kwargs = models.BinaryField(blank=True, null=True)
    output = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.QUEUED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.created_at} {'(done)' if self.completed_at is not None else ''}"
