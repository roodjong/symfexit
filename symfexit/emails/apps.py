from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EmailTemplateConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.emails"
    verbose_name = _("Email templates")
