from django.contrib import admin

from symfexit.payments.mollie.models import MollieCustomer, MolliePayment, MollieSettings


class MollieCustomerInline(admin.TabularInline):
    model = MollieCustomer
    extra = 0
    max_num = 1
    fields = ("mollie_customer_id", "created_at")
    readonly_fields = ("mollie_customer_id", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MollieCustomer)
class MollieCustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "mollie_customer_id", "created_at")
    readonly_fields = ("user", "mollie_customer_id", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return False


class MollieSettingsInline(admin.StackedInline):
    model = MollieSettings
    extra = 0
    max_num = 1


class MolliePaymentInline(admin.TabularInline):
    model = MolliePayment
    extra = 0
    fields = ("mollie_payment_id", "status", "created_at")
    readonly_fields = ("mollie_payment_id", "status", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MolliePayment)
class MolliePaymentAdmin(admin.ModelAdmin):
    list_display = ("mollie_payment_id", "obligation", "status", "created_at")
    readonly_fields = ("mollie_payment_id", "obligation", "status", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return False
