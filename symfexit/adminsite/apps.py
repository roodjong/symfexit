from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig
from django.utils.translation import gettext_lazy as _


class MyAdminConfig(AdminConfig):
    default_site = "symfexit.adminsite.admin.get_admin_site"


# Required for the translations to be loaded
class AdminSiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.adminsite"
    verbose_name = _("Adminsite")

    def menu_items(self, request):
        if request.user.is_staff:
            return [{"name": _("Administration"), "viewname": "admin:index", "order": 3}]
        else:
            return []
