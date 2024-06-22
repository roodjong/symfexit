from django.db import models


class TailwindKey(models.Model):
    COLOR_KEY_CHOICES = [
        ("primary", "Primary Color"),
        ("secondary", "Secondary Color"),
    ]
    id = models.AutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=20, choices=COLOR_KEY_CHOICES)
    value = models.TextField()

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"

class CurrentThemeVersion(models.Model):
    id = models.AutoField(primary_key=True)
    version = models.DateTimeField(auto_now=True)

    class Meta:
        get_latest_by = "version"

    def __str__(self) -> str:
        return self.version
