from django.contrib import admin
from django.http.request import HttpRequest

from signup.models import ApplicationPayment, MembershipApplication

# Register your models here.
@admin.register(ApplicationPayment)
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

@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "status", "created_at")
    fields = (
        "created_at",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "birth_date",
        "address",
        "city",
        "postal_code",
        "preferred_group",
        "payment_amount",
        "payable",
        "status",
        "user",
    )
    readonly_fields = ("created_at", "payment_amount", "payable", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return obj.status == MembershipApplication.Status.CREATED

    def save_model(self, request, obj: MembershipApplication, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        if obj.status == MembershipApplication.Status.ACCEPTED:
            obj.user = obj.create_user()
        return super().save_model(request, obj, form, change)
