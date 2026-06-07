from django.contrib import admin

from symfexit.membership.models import MembershipTier, MembershipType


class MembershipTierInline(admin.TabularInline):
    model = MembershipTier
    extra = 1
    autocomplete_fields = ("product",)


@admin.register(MembershipType)
class MembershipTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "position")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("custom_amount_product",)
    inlines = [MembershipTierInline]
