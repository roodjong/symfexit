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

from symfexit.members.forms import MembershipSelectionForm, PasswordChangeForm, UserForm
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.models import BillingAddress, Order, Payment, PeriodUnit
from symfexit.payments.registry import payments_registry


def _friendly_period(period, unit):
    """Return a user-friendly description of a subscription period."""
    if unit == PeriodUnit.MONTH and period == 3:  # noqa: PLR2004
        return _("quarter")
    if unit == PeriodUnit.MONTH and period == 1:
        return _("month")
    if unit == PeriodUnit.YEAR and period == 1:
        return _("year")
    if unit == PeriodUnit.WEEK and period == 1:
        return _("week")
    if unit == PeriodUnit.DAY and period == 1:
        return _("day")
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
        payment_provider = ""
        if active_order:
            payment_qs = Payment.objects.filter(order=active_order).select_related(
                "transaction"
            ).order_by("-paid_at")
            payments = [
                {"paid_at": p.paid_at, "amount_euros": p.transaction.amount_cents / 100}
                for p in payment_qs
            ]
            subscription_period = _friendly_period(
                active_order.subscription_period,
                active_order.subscription_period_unit,
            )
            payment_provider = payments_registry.get_main().description()

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
            Prefetch("tiers", queryset=MembershipTier.objects.filter(enabled=True).select_related("product"))
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
                "minimum_custom_amount_euros": str(mt.custom_amount_product.price_euros) if mt.custom_amount_product else None,
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
        messages.error(request, _("No membership type is configured for your account. Please contact the administrator."))
        return redirect("members:memberdata")

    billing_address = BillingAddress.get_or_create_for_user(user)
    if billing_address is None:
        messages.error(request, _("Please fill in your address, city, and postal code before starting a subscription."))
        return redirect("members:memberdata")

    _order, obligation = Order.objects.create_with_obligation(
        product=product,
        billing_address=billing_address,
        for_user=user,
        price_euros=price_euros,
    )

    provider = payments_registry.get_main()
    return provider.start_payment_flow(
        request, obligation, reverse("members:memberdata")
    )


def payment_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return redirect("login")
    return _start_payment(request)
