from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from symfexit.tenants.adminsite import global_admin
from symfexit.tenants.models import Client, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


@admin.register(Client, site=global_admin)
class ClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    inlines = (DomainInline,)
