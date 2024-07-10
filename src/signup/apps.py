from django.apps import AppConfig

from django.utils.translation import gettext_lazy as _


class SignupConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "signup"
    verbose_name = _("Signup")
