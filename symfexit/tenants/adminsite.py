from django.contrib.admin import AdminSite


class GlobalAdminSite(AdminSite):
    site_header = "Symfexit Management"
    site_title = "Symfexit Management Portal"
    index_title = "Welcome to the Symfexit Management Portal"


global_admin = GlobalAdminSite(name="global_admin")
