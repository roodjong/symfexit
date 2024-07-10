import uuid

from django.db import models

from django.utils.translation import gettext_lazy as _


class FileNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField(_("name"))
    parent = models.ForeignKey(
        "Directory",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        verbose_name=_("parent directory"),
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    def save(self, *args, **kwargs):
        if isinstance(self.parent, File):
            return  # Files cannot be parents
        if self.parent == self:
            return
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


def file_location(instance, filename):
    return f"{instance.id}"


class File(FileNode):
    content = models.FileField(_("content"), upload_to=file_location)
    size = models.IntegerField(_("size"), default=0)
    content_type = models.TextField(_("content type"), default="application/octet-stream")

    def url(self):
        return self.content.url

    def human_size(self):
        if self.size < 1024:
            return f"{self.size} bytes"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.2f} KiB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.2f} MiB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.2f} GiB"

    def __str__(self) -> str:
        return "File: " + self.name

    class Meta:
        verbose_name = _("file")
        verbose_name_plural = _("files")

class Directory(FileNode):
    class Meta:
        verbose_name_plural = "directories"

    def __str__(self) -> str:
        return "Directory: " + self.name

    class Meta:
        verbose_name = _("directory")
        verbose_name_plural = _("directories")
