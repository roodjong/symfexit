import zoneinfo

from django import forms
from django.contrib import admin
from django.forms import ValidationError
from django_tenants.admin import TenantAdminMixin

from symfexit.tenants.adminsite import global_admin
from symfexit.tenants.models import Client, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


class ClientAdminForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name", "payments_time_zone")

    def clean_payments_time_zone(self, *args, **kwargs):
        value = self.cleaned_data["payments_time_zone"]
        try:
            zoneinfo.ZoneInfo(value)
        except Exception:
            raise ValidationError("Invalid time zone") from None
        return value


@admin.register(Client, site=global_admin)
class ClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    form = ClientAdminForm
    list_display = ("name",)
    inlines = (DomainInline,)
