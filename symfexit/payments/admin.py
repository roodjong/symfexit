from django.contrib import admin

from symfexit.payments.models import BillingAddress, Subscription

# Register your models here.
# @admin.register(Order)
# class OrderAdmin(admin.ModelAdmin):
#     # show the eid
#     list_display = ("eid", "price", "description", "payment_status")
#     # show the eid in the detail display as a readonly field
#     readonly_fields = ("eid", "price", "description", "payment_status")

#     # don't show the add button
#     def has_add_permission(self, request):
#         return False

#     # don't show the delete button
#     def has_delete_permission(self, request, obj: Order = None):
#         if obj is None:
#             return False
#         return obj.payment_status == Order.Status.EXPIRED

#     # don't show the change button
#     def has_change_permission(self, request, obj=None):
#         return False


@admin.register(BillingAddress)
class BillingAddressAdmin(admin.ModelAdmin):
    search_fields = ("id", "name")
    list_display = ("id", "name", "address", "city")
    fields = ("name", "address", "city", "postal_code", "user")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "eid",
        "name",
        "description",
        "price_per_period",
        "period_quantity",
        "period_unit",
        "created_at",
        "updated_at",
    )
