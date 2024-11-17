from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.members"
    verbose_name = _("Members")

    def menu_items(self):
        return [
            {"name": _("Details"), "viewname": "members:memberdata", "order": 1},
            {"name": _("Log out"), "viewname": "members:logout", "order": 3},
        ]
