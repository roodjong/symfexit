from django.contrib import admin
from django.utils.safestring import mark_safe
from django_tenants.admin import TenantAdminMixin

from symfexit.tenants.adminsite import global_admin
from symfexit.tenants.models import Client, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


@admin.register(Client, site=global_admin)
class ClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "site_title", "main_site", "homepage_current")
    fields = (
        "name",
        "site_title",
        "logo_image",
        "main_site",
        "homepage_current",
        "payment_tiers_json",
    )
    inlines = (DomainInline,)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Override formfield to display the current logo image in the admin when editing a tenant.
        """
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "logo_image":
            obj_id = request.resolver_match.kwargs.get("object_id")
            if obj_id:
                try:
                    obj = self.model.objects.get(pk=obj_id)
                    if obj.logo_image:
                        img_html = mark_safe(
                            f'<img src="{obj.logo_image.url}" style="max-height: 50px; max-width: 100px; margin-bottom: 10px;" /><br>'
                        )
                        formfield.help_text = img_html
                except self.model.DoesNotExist:
                    pass
        return formfield
