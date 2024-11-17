from django.db import models
from django.utils.translation import gettext_lazy as _
from tinymce.models import HTMLField


class HomePage(models.Model):
    title = models.CharField(_("Title"), max_length=50, blank=True)
    content = HTMLField(_("Content"))
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("home page")
        verbose_name_plural = _("home pages")

    def __str__(self):
        return self.title
