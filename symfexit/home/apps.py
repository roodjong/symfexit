from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HomeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.home"
    verbose_name = _("Home")

    def menu_items(self, request):
        return [{"name": _("Home"), "viewname": "home:home", "order": 0}]
