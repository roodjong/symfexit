from django.apps import AppConfig

from django.utils.translation import gettext_lazy as _


class MembershipConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "membership"
    verbose_name = _("Membership")
