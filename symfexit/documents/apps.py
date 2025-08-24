from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.documents"
    verbose_name = _("Documents")

    def menu_items(self, request):
        return [{"name": _("Documents"), "viewname": "documents:documents", "order": 2}]
