import json

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.membership.forms import PaymentTier, PaymentTierInfo
from symfexit.membership.models import Membership
from symfexit.payments.models import Order


def save_new_tiers(tiers):
    tiers = list(filter(lambda x: x != {}, tiers))
    tiers = list(filter(lambda x: not x.get("DELETE", False), tiers))
    tiers = [
        {
            "help_text": x["help_text"],
            "cents_per_period": int(x["cents_per_period"] * 100),
        }
        for x in tiers
    ]
    # config.PAYMENT_TIERS_JSON = json.dumps(list(tiers))


class PaymentTiersAdmin(admin.ModelAdmin):
    change_list_template = "admin/membership/payment_tiers.html"

    def __init__(self, model, admin_site):
        model._meta.concrete_model = PaymentTiers
        super().__init__(model, admin_site)

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.module_name
        return [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="%s_%s_changelist" % info,
            ),
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="%s_%s_add" % info,
            ),
        ]

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        initial = json.loads(config.PAYMENT_TIERS_JSON)

        PaymentTierFormSet = forms.formset_factory(PaymentTier, extra=1, can_delete=True)

        if request.method == "POST" and request.user.has_perm("membership.change_config"):
            payment_tier_info = PaymentTierInfo(request.POST, prefix="info")
            form = PaymentTierFormSet(request.POST, initial=initial, prefix="tiers")
            if form.is_valid():
                print(form.cleaned_data)
                save_new_tiers(form.cleaned_data)
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    _("Live settings updated successfully."),
                )
                return HttpResponseRedirect(".")
            else:
                messages.add_message(
                    request,
                    messages.ERROR,
                    _("Failed to update live settings."),
                )
        else:
            payment_tier_info = PaymentTierInfo(initial={}, prefix="info")
            form = PaymentTierFormSet(initial=initial, prefix="tiers")

        context = dict(
            self.admin_site.each_context(request),
            app_label="membership",
            title=_("Payment Tiers"),
            opts=self.model._meta,
            formset=form,
            info_form=payment_tier_info,
            media=self.media + form.media,
        )
        request.current_app = self.admin_site.name
        return TemplateResponse(request, self.change_list_template, context)

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj)


class PaymentTiers:
    class Meta:
        app_label = "membership"
        object_name = "Payment Tiers"
        concrete_model = None
        model_name = module_name = "paymenttiers"
        verbose_name_plural = _("payment tiers")
        abstract = False
        swapped = False

        def get_ordered_objects(self):
            return False

        def get_change_permission(self):
            return "change_%s" % self.model_name

        @property
        def app_config(self):
            return apps.get_app_config(self.app_label)

        @property
        def label(self):
            return "%s.%s" % (self.app_label, self.object_name)

        @property
        def label_lower(self):
            return "%s.%s" % (self.app_label, self.model_name)

    _meta = Meta()


admin.site.register([PaymentTiers], PaymentTiersAdmin)


class OrderInlineForm(forms.ModelForm):
    model = Order

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.payment_status == Order.Status.PAID:
            for field in self.fields.values():
                field.disabled = True


class OrderInline(admin.StackedInline):
    model = Order
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("address",)
    form = OrderInlineForm


class IsCurrentFilter(admin.SimpleListFilter):
    title = _("is current")
    parameter_name = "is_current"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(active_from_to__contains=timezone.now())
        if self.value() == "no":
            return queryset.exclude(active_from_to__contains=timezone.now())


class HasUserFilter(admin.SimpleListFilter):
    title = _("has user")
    parameter_name = "has_user"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(user=None)
        if self.value() == "no":
            return queryset.filter(user=None)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    inlines = (OrderInline,)
    list_filter = (IsCurrentFilter, HasUserFilter)
