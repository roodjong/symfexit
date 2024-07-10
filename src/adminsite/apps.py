from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig

from django.utils.translation import gettext_lazy as _


class MyAdminConfig(AdminConfig):
    default_site = "adminsite.admin.get_admin_site"


# Required for the translations to be loaded
class AdminSiteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "adminsite"
    verbose_name = _("Adminsite")
