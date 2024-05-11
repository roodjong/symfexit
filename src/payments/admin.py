from django.contrib import admin

from payments.models import BillingAddress, Order


# Register your models here.
@admin.register(Order)
class PayableAdmin(admin.ModelAdmin):
    # show the eid
    list_display = ("eid", "price", "description", "payment_status")
    # show the eid in the detail display as a readonly field
    readonly_fields = ("eid", "price", "description", "payment_status")
    # don't show the add button
    def has_add_permission(self, request):
        return False
    # don't show the delete button
    def has_delete_permission(self, request, obj=None):
        return False
    # don't show the change button
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(BillingAddress)
class BillingAddressAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "address", "city")
    fields = ("name", "address", "city", "postal_code", "user")
