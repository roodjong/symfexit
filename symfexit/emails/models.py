from django.db import models
from django.utils.translation import gettext_lazy as _
from froala_editor.fields import FroalaField

from symfexit.emails.template_manager import LayoutManager, TemplateManager


class EmailLayout(models.Model):
    id = models.AutoField(primary_key=True)
    template = models.CharField(
        _("template"),
        unique=True,
        blank=False,
        max_length=80,
        choices=LayoutManager.get_template_choices(),
    )
    # we could add language as well and make template + language a unique key
    body = FroalaField(
        _("body"),
    )

    text_body = models.TextField(_("Text body"))

    def __str__(self) -> str:
        return f"{self.template}"


class EmailTemplate(models.Model):
    id = models.AutoField(primary_key=True)
    layout = models.ForeignKey(
        "EmailLayout",
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
        verbose_name=_("email layout"),
    )
    template = models.CharField(
        _("template"),
        unique=True,
        blank=False,
        max_length=80,
        choices=TemplateManager.get_template_choices(),
    )
    # we could add language as well and make template + langauge a unique key
    from_email = models.EmailField(_("From email"))
    subject = models.TextField(_("subject"))
    body = FroalaField(
        _("body"),
    )

    text_body = models.TextField(_("Text body"))

    def __str__(self) -> str:
        return f"{self.template}: {self.subject}"
