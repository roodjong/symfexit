from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.events"
    verbose_name = _("Events")

    def menu_items(self, request):
        from symfexit.members.models import User  # noqa:PLC0415

        if request.user.member_type == User.MemberType.MEMBER:
            return [{"name": _("Events"), "viewname": "events:events", "order": 2}]
        else:
            return []
