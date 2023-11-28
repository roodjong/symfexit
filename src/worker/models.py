from django.db import models


class Task(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_COMPLETED = "completed"
    STATUS_ERROR_UNKNOWN_TASK = "not_registered"
    STATUS_EXCEPTION = "exception"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ERROR_UNKNOWN_TASK, "Unknown task (not registered)"),
        (STATUS_EXCEPTION, "Exception"),
    ]
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=20)
    output = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.created_at} {'(done)' if self.completed_at is not None else ''}"
