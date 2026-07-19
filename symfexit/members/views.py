import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import FormView, TemplateView

from symfexit.members.forms import (
    MembershipCancellationForm,
    MembershipSelectionForm,
    PasswordChangeForm,
    UserForm,
)
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.models import BillingAddress, Order, Payment, PeriodUnit
from symfexit.payments.registry import payments_registry


def friendly_period(period, unit):
    """Return a user-friendly description of a subscription period."""
    if unit == PeriodUnit.MONTH:
        if period == 1:
            return _("month")
        elif period == 3:  # noqa: PLR2004
            return _("quarter")
        else:
            return _("{} months").format(period)
    elif unit == PeriodUnit.YEAR:
        if period == 1:
            return _("year")
        else:
            return _("{} years").format(period)
    elif unit == PeriodUnit.WEEK:
        if period == 1:
            return _("week")
        else:
            return _("{} weeks").format(period)
    elif unit == PeriodUnit.DAY:
        if period == 1:
            return _("day")
        else:
            return _("{} days").format(period)
    unit_display = PeriodUnit(unit).label.lower()
    return f"{period} {unit_display}"


class MemberData(LoginRequiredMixin, TemplateView):
    template_name = "members/user_form.html"

    def get(self, request, *args, **kwargs):
        user_form = UserForm(instance=request.user, prefix="user_form")
        password_form = PasswordChangeForm(user=request.user, prefix="password_form")

        active_order = Order.objects.filter(
            ordered_for=request.user, cancelled_at__isnull=True
        ).first()

        payments = []
        subscription_period = ""
        payment_provider = _("an unknown provider")
        can_change_bank_account = False
        if active_order:
            payment_qs = (
                Payment.objects.filter(obligation__order=active_order)
                .select_related("transaction")
                .order_by("-paid_at")
            )
            payments = [
                {"paid_at": p.paid_at, "amount_euros": p.transaction.amount_cents / 100}
                for p in payment_qs
            ]
            subscription_period = friendly_period(
                active_order.subscription_period,
                active_order.subscription_period_unit,
            )
            if active_order.paid_using:
                payment_provider = active_order.paid_using.get_processor().name()
                instance = payments_registry.get_instance_for_provider(active_order.paid_using)
                can_change_bank_account = instance.supports_bank_account_change()

        return render(
            request,
            self.template_name,
            {
                "user_form": user_form,
                "password_form": password_form,
                "active_order": active_order,
                "payments": payments,
                "subscription_period": subscription_period,
                "payment_provider": payment_provider,
                "can_change_bank_account": can_change_bank_account,
            },
        )

    def post(self, request, *args, **kwargs):
        if "user_form" in request.POST:
            user_form = UserForm(request.POST, instance=request.user, prefix="user_form")
            if user_form.is_valid():
                user_form.save()
                return redirect("members:memberdata")
            else:
                password_form = PasswordChangeForm(user=request.user, prefix="password_form")
                return render(
                    request,
                    self.template_name,
                    {"user_form": user_form, "password_form": password_form},
                )
        elif "password_form" in request.POST:
            password_form = PasswordChangeForm(
                request.POST, user=request.user, prefix="password_form"
            )
            if password_form.is_valid():
                password_form.save()
                return redirect("members:memberdata")
            else:
                user_form = UserForm(instance=request.user, prefix="user_form")
                return render(
                    request,
                    self.template_name,
                    {"user_form": user_form, "password_form": password_form},
                )
        else:
            raise ValueError("Invalid form")


class Logout(TemplateView):
    template_name = "members/logout.html"

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("home:home")


class MembershipSelection(LoginRequiredMixin, FormView):
    template_name = "members/membership_selection.html"
    form_class = MembershipSelectionForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        membership_types = MembershipType.objects.filter(enabled=True).prefetch_related(
            Prefetch(
                "tiers",
                queryset=MembershipTier.objects.filter(enabled=True).select_related("product"),
            )
        )

        tiers_data = {}
        for mt in membership_types:
            tiers_list = []
            for tier in mt.tiers.all():
                tiers_list.append(
                    {
                        "pk": tier.pk,
                        "name": tier.name,
                        "price_cents": tier.price_cents(),
                        "price_euros": str(tier.price_euros()),
                    }
                )
            tiers_data[mt.pk] = {
                "tiers": tiers_list,
                "allow_custom_amount": mt.allow_custom_amount,
                "minimum_custom_amount_euros": str(mt.custom_amount_product.price_euros)
                if mt.custom_amount_product
                else None,
            }

        context["tiers_json"] = json.dumps(tiers_data)
        return context

    def form_valid(self, form):
        form.save(self.request.user)
        return _start_payment(self.request)


def _start_payment(request):
    user = request.user

    if user.membership_tier is not None:
        product = user.membership_tier.product
        price_euros = product.price_euros
    elif user.membership_type is not None and user.membership_type.custom_amount_product:
        product = user.membership_type.custom_amount_product
        price_euros = product.price_euros
    else:
        messages.error(
            request,
            _(
                "No membership type is configured for your account. Please contact the administrator."
            ),
        )
        return redirect("members:memberdata")

    billing_address = BillingAddress.get_or_create_for_user(user)
    if billing_address is None:
        messages.error(
            request,
            _("Please fill in your address, city, and postal code before starting a subscription."),
        )
        return redirect("members:memberdata")

    default_provider = payments_registry.get_default_provider()

    # A member has at most one running subscription. Reuse the active order if
    # it still matches the chosen product and price; cancel any others so only
    # one order keeps generating payment obligations.
    order = None
    for active_order in Order.objects.filter(ordered_for=user, cancelled_at__isnull=True):
        if (
            order is None
            and active_order.product_id == product.id
            and active_order.product_price_euros == price_euros
            and active_order.paid_using is not None
        ):
            order = active_order
        else:
            active_order.cancel()

    if order is None:
        order, obligation = Order.objects.create_with_obligation(
            product=product,
            billing_address=billing_address,
            for_user=user,
            price_euros=price_euros,
            paid_using=default_provider,
        )
    else:
        obligation = order.get_or_create_next_payment_obligation()

    instance = payments_registry.get_instance_for_provider(order.paid_using)
    return instance.start_payment_flow(request, obligation, reverse("members:memberdata"))


def payment_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return redirect("login")
    return _start_payment(request)


class BankAccountChange(LoginRequiredMixin, TemplateView):
    template_name = "members/bank_account_change.html"

    def _get_order_and_instance(self, request):
        active_order = Order.objects.filter(
            ordered_for=request.user, cancelled_at__isnull=True
        ).first()
        if active_order is None or active_order.paid_using is None:
            messages.error(
                request, _("You have no active subscription to change the bank account for.")
            )
            return None, None

        instance = payments_registry.get_instance_for_provider(active_order.paid_using)
        if not instance.supports_bank_account_change():
            messages.error(
                request,
                _("Changing your bank account is not supported for your payment method."),
            )
            return None, None

        return active_order, instance

    def get(self, request, *args, **kwargs):
        active_order, instance = self._get_order_and_instance(request)
        if instance is None:
            return redirect("members:memberdata")
        return render(request, self.template_name, {"active_order": active_order})

    def post(self, request, *args, **kwargs):
        active_order, instance = self._get_order_and_instance(request)
        if instance is None:
            return redirect("members:memberdata")

        obligation = active_order.get_or_create_next_payment_obligation()
        return instance.start_bank_account_change_flow(
            request, obligation, reverse("members:memberdata")
        )


class MembershipCancellation(LoginRequiredMixin, FormView):
    template_name = "members/membership_cancellation.html"
    form_class = MembershipCancellationForm

    def get(self, request, *args, **kwargs):
        cancel_form = MembershipCancellationForm(user=request.user, prefix="cancel_form")

        return render(
            request,
            self.template_name,
            {
                "cancel_form": cancel_form,
            },
        )

    def post(self, request, *args, **kwargs):
        if "cancel_form" in request.POST:
            cancel_form = MembershipCancellationForm(
                request.POST, user=request.user, prefix="cancel_form"
            )
            if cancel_form.is_valid():
                cancel_form.save()
                return redirect("login")
            else:
                cancel_form = MembershipCancellationForm(user=request.user, prefix="cancel_form")
                return render(
                    request,
                    self.template_name,
                    {"cancel_form": cancel_form},
                )
        else:
            raise ValueError("Invalid form")
