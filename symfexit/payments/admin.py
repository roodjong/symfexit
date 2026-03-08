import zoneinfo
from datetime import timedelta

from django import forms
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.widgets import FilteredSelectMultiple, RelatedFieldWidgetWrapper
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.payments.models import (
    Account,
    BillingAddress,
    GeneralLedger,
    Order,
    Payment,
    PaymentObligation,
    PaymentProvider,
    Product,
    Subscription,
    Transaction,
)
from symfexit.payments.registry import payments_registry

User = get_user_model()


@admin.register(BillingAddress)
class BillingAddressAdmin(admin.ModelAdmin):
    search_fields = ("id", "name")
    list_display = ("id", "name", "address", "city")
    fields = ("name", "address", "city", "postal_code", "user")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SubscriptionInline(admin.StackedInline):
    model = Subscription
    can_delete = False
    min_num = 1
    max_num = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [SubscriptionInline]
    search_fields = ("name", "sku")


class GeneralLedgerForm(forms.ModelForm):
    account_set = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(),
        required=False,
        widget=RelatedFieldWidgetWrapper(
            FilteredSelectMultiple("accounts", is_stacked=False),
            rel=Account._meta.get_field("general_ledger").remote_field,
            admin_site=admin.site,
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["account_set"].initial = self.instance.account_set.all()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
        instance.account_set.set(self.cleaned_data["account_set"])
        return instance


@admin.register(GeneralLedger)
class GeneralLedgerAdmin(admin.ModelAdmin):
    form = GeneralLedgerForm
    readonly_fields = ("balance_cents",)
    list_display = ("__str__", "balance_cents")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    readonly_fields = ("balance_cents",)
    fields = ("name", "code", "description", "credit_balance", "balance_cents")
    list_display = ("__str__", "balance_cents")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "__str__")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RawTextWidget(forms.TextInput):
    template_name = "admin/widgets/raw_text.html"

    def __init__(self, label, attrs=None):
        super().__init__(attrs)
        self.label = label

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"].update({"label": self.label})
        return context


class PaymentObligationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        parent_obj = kwargs.pop("parent_obj")
        super().__init__(*args, **kwargs)
        if parent_obj is not None and not self.instance.pk:
            self.fields[
                "ordered_for_billing_address"
            ].initial = parent_obj.ordered_for_billing_address.id
            self.fields["amount_euros"].initial = parent_obj.product.price_euros
        if self.instance.pk is not None:
            self.fields["ordered_for_billing_address"].widget = RawTextWidget(
                label=str(self.instance.ordered_for_billing_address)
            )


class PaymentObligationInline(admin.TabularInline):
    model = PaymentObligation
    readonly_fields = ("pay_before", "transaction")
    extra = 0
    form = PaymentObligationForm
    show_change_link = True

    def get_formset(self, request, obj=None, **kwargs):
        # First get the base formset class
        BaseFormSet = kwargs.pop("formset", self.formset)

        # Now make a custom subclass with an overridden “get_form_kwargs()”
        class CustomFormSet(BaseFormSet):
            def get_form_kwargs(self, index):
                kwargs = super().get_form_kwargs(index)
                kwargs["parent_obj"] = obj
                return kwargs

        # Finally, pass our custom subclass to the superclass’s method. This
        # will override the default.
        kwargs["formset"] = CustomFormSet
        return super().get_formset(request, obj, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(~Exists(Payment.objects.filter(obligation=OuterRef("pk"))))


class PaidPaymentObligationInline(admin.TabularInline):
    model = PaymentObligation
    extra = 0
    verbose_name = _("Paid payment obligation")
    verbose_name_plural = _("Paid payment obligations")
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(Exists(Payment.objects.filter(obligation=OuterRef("pk"))))


class PaymentInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["paid_at"].initial = timezone.now()


class PaymentInline(admin.TabularInline):
    model = Payment
    form = PaymentInlineForm
    readonly_fields = ("transaction",)
    extra = 0
    show_change_link = True

    def has_change_permission(self, request, obj=...):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "obligation" and hasattr(self, "parent_obj"):
            kwargs["queryset"] = PaymentObligation.objects.filter(order=self.parent_obj).filter(
                ~Exists(Payment.objects.filter(obligation=OuterRef("pk")))
            )
        if db_field.name == "paid_using":
            manual_types = [
                name for name, processor in payments_registry if processor.allows_manual_payments()
            ]
            kwargs["queryset"] = PaymentProvider.objects.filter(type__in=manual_types)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_formset(self, request, obj=None, **kwargs):
        self.parent_obj = obj
        return super().get_formset(request, obj, **kwargs)


class OrderStatusFilter(SimpleListFilter):
    title = _("status")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [(None, _("Active")), ("cancelled", _("Cancelled")), ("all", _("All"))]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset.filter(cancelled_at__isnull=True)
        if self.value() == "cancelled":
            return queryset.filter(cancelled_at__isnull=False)
        return queryset

    def choices(self, cl):
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == lookup,
                "query_string": cl.get_query_string(
                    {self.parameter_name: lookup},
                    [],
                ),
                "display": title,
            }


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    change_form_template = "admin/payments/change_form.html"
    delete_confirmation_template = "admin/payments/order_cancel_confirm.html"
    autocomplete_fields = ("ordered_for", "ordered_for_billing_address")
    inlines = (PaidPaymentObligationInline, PaymentObligationInline, PaymentInline)
    list_display = ("product_name", "ordered_for", "created_at", "cancelled_at")
    list_filter = (OrderStatusFilter,)
    show_change_link = True

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return self.readonly_fields + (
                "product",
                "product_name",
                "product_sku",
                "subscription",
                "subscription_period_unit",
                "subscription_period",
                "ordered_for",
                "cancelled_at",
            )
        return super().get_readonly_fields(request, obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context.update({"delete_is_cancel": True})
        return super().render_change_form(request, context, add, change, form_url, obj)

    def delete_model(self, request, obj):
        obj.cancel()

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.cancelled_at is not None:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, PaymentObligation) and not instance.pk:
                ar_account, _ = Account.get_accounts_receivable_account()
                revenue_account, _ = Account.get_revenue_account()
                transaction = Transaction.objects.create(
                    credit_account=revenue_account,
                    debit_account=ar_account,
                    amount_cents=int(instance.order.product_price_euros * 100),
                )
                instance.transaction = transaction
                if not instance.pay_before:
                    order = instance.order
                    instance.pay_before = order._period_to_datetime(
                        *order._calculate_next_period(instance.year, instance.period),
                        timezone=zoneinfo.ZoneInfo(request.tenant.payments_timezone),
                    ) - timedelta(seconds=1)
            elif isinstance(instance, Payment) and not instance.pk:
                ar_account, _ = Account.get_accounts_receivable_account()
                credit_to = (
                    instance.paid_using.credit_to_account
                    if instance.paid_using
                    else Account.get_bank_account()[0]
                )
                transaction = Transaction.objects.create(
                    credit_account=ar_account,
                    debit_account=credit_to,
                    amount_cents=int(instance.order.product_price_euros * 100),
                )
                instance.transaction = transaction
            instance.save()
        formset.save_m2m()


def load_product_info(request, product_id=None):
    product = get_object_or_404(Product.objects.select_related("subscription"), id=product_id)
    return JsonResponse(
        {
            "product_sku": product.sku,
            "product_name": product.name,
            "product_price_euros": product.price_euros,
            "subscription": product.subscription.id,
            "subscription_period_unit": product.subscription.period_unit,
            "subscription_period": product.subscription.period,
        }
    )


def get_or_create_billing_address(request, user_id):
    user = get_object_or_404(User, id=user_id)
    address = BillingAddress.get_or_create_for_user(user)
    if not address:
        return JsonResponse({"message": _("User has not setup full address yet")})
    return JsonResponse({"billing_address_id": address.id, "full_name": str(address)})


class PaymentObligationPaymentInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and "paid_at" in self.fields:
            self.fields["paid_at"].initial = timezone.now()


class PaymentObligationPaymentInline(admin.TabularInline):
    model = Payment
    form = PaymentObligationPaymentInlineForm
    extra = 0

    def get_fields(self, request, obj=None):
        if obj and obj.payment_set.exists():
            return ("order", "transaction", "paid_using", "paid_at")
        return ("paid_using", "paid_at")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.payment_set.exists():
            return ("order", "transaction", "paid_using", "paid_at")
        return ()

    def has_add_permission(self, request, obj=None):
        if obj and obj.payment_set.exists():
            return False
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "paid_using":
            manual_types = [
                name for name, processor in payments_registry if processor.allows_manual_payments()
            ]
            kwargs["queryset"] = PaymentProvider.objects.filter(type__in=manual_types)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PaymentObligation)
class PaymentObligationAdmin(admin.ModelAdmin):
    readonly_fields = ("transaction", "order")
    inlines = (PaymentObligationPaymentInline,)

    def has_module_permission(self, request):
        return False

    def _has_payment(self, obj):
        return obj and obj.payment_set.exists()

    def has_change_permission(self, request, obj=None):
        if self._has_payment(obj):
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if self._has_payment(obj):
            return False
        return True

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        obligation = form.instance
        for instance in instances:
            if isinstance(instance, Payment) and not instance.pk:
                ar_account, _ = Account.get_accounts_receivable_account()
                credit_to = (
                    instance.paid_using.credit_to_account
                    if instance.paid_using
                    else Account.get_bank_account()[0]
                )
                transaction = Transaction.objects.create(
                    credit_account=ar_account,
                    debit_account=credit_to,
                    amount_cents=int(obligation.amount_euros * 100),
                )
                instance.transaction = transaction
                instance.order = obligation.order
                instance.obligation = obligation
            instance.save()
        formset.save_m2m()

    def changelist_view(self, request, extra_context=None):
        return redirect("admin:index")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect("admin:index")


class PaymentProviderAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            choices = [
                (name, provider.name())
                for name, provider in payments_registry
                if provider.can_install()
            ]
            # Keep the current type in the dropdown even if no longer installable
            if self.instance.pk and self.instance.type:
                if not any(name == self.instance.type for name, _ in choices):
                    provider = payments_registry.get(self.instance.type)
                    if provider:
                        choices.append((self.instance.type, provider.name()))
            self.fields["type"].widget = forms.Select(choices=[("", "---"), *choices])


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    form = PaymentProviderAdminForm
    list_display = ("name", "type")

    def get_inlines(self, request, obj):
        if obj and obj.type:
            provider = payments_registry.get(obj.type)
            if provider:
                inline = provider.get_settings_inline()
                if inline:
                    return [inline]
        return []

    def save_model(self, request, obj, form, change):
        if obj.default:
            PaymentProvider.objects.filter(default=True).update(default=False)
        return super().save_model(request, obj, form, change)
