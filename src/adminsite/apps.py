from django.contrib.admin.apps import AdminConfig

from adminsite.admin import admin_site


class MyAdminConfig(AdminConfig):
    default_site = "adminsite.admin.get_admin_site"
