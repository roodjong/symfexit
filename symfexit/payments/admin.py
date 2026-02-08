from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple, RelatedFieldWidgetWrapper
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
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
        context.update({"widget": {"label": self.label}})
        return context


class PaymentObligationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        parent_obj = kwargs.pop("parent_obj")
        super().__init__(*args, **kwargs)
        if parent_obj is not None:
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
    readonly_fields = ("pay_before",)
    extra = 0
    form = PaymentObligationForm

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


class PaymentInline(admin.TabularInline):
    model = Payment
    readonly_fields = ("paid_at",)
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    change_form_template = "admin/payments/change_form.html"
    autocomplete_fields = ("ordered_for", "ordered_for_billing_address")
    inlines = (PaymentObligationInline, PaymentInline)
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
            )
        return super().get_readonly_fields(request, obj)


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


class PaymentProviderAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["type"].widget = forms.Select(
                choices=[
                    ("", "---"),
                    *((name, provider.description()) for name, provider in payments_registry),
                ]
            )


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    form = PaymentProviderAdminForm
    list_display = ("type",)

    def get_inlines(self, request, obj):
        inlines = []
        for _, provider in payments_registry:
            inline = provider.get_settings_inline()
            if inline is not None:
                inlines.append(inline)

        return inlines
