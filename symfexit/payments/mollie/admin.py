from django.contrib import admin
from django.utils.html import format_html_join

from symfexit.payments.mollie.models import MollieCustomer, MolliePayment, MollieSettings


@admin.display(description="Refunds and chargebacks")
def refunds_and_chargebacks(mollie_payment):
    reversals = mollie_payment.reversals.order_by("created_at")
    if not reversals:
        return "-"
    return format_html_join(
        "<br>",
        "{}: {} of €{}, {}",
        (
            (
                r.mollie_id,
                r.get_kind_display().lower(),
                f"{r.amount_cents / 100:.2f}",
                _reversal_state(r),
            )
            for r in reversals
        ),
    )


def _reversal_state(reversal):
    if reversal.chargeback_reversed_at:
        return "booked, then reversed by the bank"
    if reversal.processed_at:
        return "booked"
    # Refunds aren't booked until Mollie has paid them out.
    return reversal.status or "not booked"


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
    fields = ("mollie_payment_id", "status", "created_at", refunds_and_chargebacks)
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MolliePayment)
class MolliePaymentAdmin(admin.ModelAdmin):
    list_display = ("mollie_payment_id", "obligation", "status", "created_at")
    readonly_fields = (
        "mollie_payment_id",
        "obligation",
        "status",
        "created_at",
        refunds_and_chargebacks,
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return False
