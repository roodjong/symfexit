from django.db import models
from django.utils.translation import gettext_lazy as _
from django_prose_editor.fields import ProseEditorField

from symfexit.emails.template_manager import TemplateManager


class EmailTemplate(models.Model):
    id = models.AutoField(primary_key=True)
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
    body = ProseEditorField(
        _("body"),
        extensions={
            # Core text formatting
            "Bold": True,
            "Italic": True,
            "Strike": True,
            "Underline": True,
            "HardBreak": True,
            # Structure
            "Heading": {
                "levels": [1, 2, 3]  # Only allow h1, h2, h3
            },
            "BulletList": True,
            "OrderedList": True,
            "ListItem": True,  # Used by BulletList and OrderedList
            "Blockquote": True,
            # Advanced extensions
            "Link": {
                "enableTarget": True,  # Enable "open in new window"
                "protocols": ["http", "https", "mailto"],  # Limit protocols
            },
            "Table": True,
            "TableRow": True,
            "TableHeader": True,
            "TableCell": True,
            # Editor capabilities
            "History": True,  # Enables undo/redo
            "HTML": True,  # Allows HTML view
            "Typographic": True,  # Enables typographic chars
        },
        sanitize=True,  # Recommended to enable sanitization
    )

    text_body = models.TextField(_("Text body"))

    def __str__(self) -> str:
        return f"{self.template}: {self.subject}"
