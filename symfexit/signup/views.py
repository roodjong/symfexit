import json
import logging

from django.conf import settings
from django.contrib.auth import logout
from django.db.models import Prefetch
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.views.generic import FormView

from symfexit.emails._templates.emails.membership_application import MembershipApplicationEmail
from symfexit.emails._templates.render import send_email
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.registry import payments_registry
from symfexit.signup.forms import SignupForm
from symfexit.signup.models import MembershipApplication

logger = logging.getLogger(__name__)


class MemberSignup(FormView):
    template_name = "signup/signup.html"
    success_url = reverse_lazy("signup:payment")
    form_class = SignupForm

    def dispatch(self, *args, initialgroup: str | None = None, **kwargs):
        self.initialgroup = initialgroup
        return super().dispatch(*args, **kwargs)

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
                tier: MembershipTier
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
        context["signup_available"] = bool(tiers_data)
        context["development"] = settings.SYMFEXIT_ENV == "development"
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.initialgroup:
            kwargs["initialgroup"] = self.initialgroup
        return kwargs

    def form_valid(self, form):
        logout(self.request)
        application = form.save()
        send_email(
            MembershipApplicationEmail({"firstname": application.first_name}), application.email
        )
        return HttpResponseRedirect(reverse("signup:payment", args=[application.eid]))


def member_signup_pay(request, application_id):
    default_provider = payments_registry.get_default_provider()
    application = MembershipApplication.get_or_404(application_id)
    order, obligation = application.get_or_create_order(default_provider)
    instance = payments_registry.get_instance_for_provider(order.paid_using)
    return instance.start_payment_flow(
        request, obligation, reverse("signup:return", args=[application.eid])
    )


def member_signup_pay_retry(request, application_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    application = MembershipApplication.get_or_404(application_id)
    default_provider = payments_registry.get_default_provider()
    order, obligation = application.get_or_create_order(default_provider)
    instance = payments_registry.get_instance_for_provider(order.paid_using)
    return instance.start_payment_flow(
        request, obligation, reverse("signup:return", args=[application.eid])
    )


def return_view(request, application_id):
    application = MembershipApplication.get_or_404(application_id)
    order = application._order
    if order is None:
        logger.warning(f"Order not found for application {application_id}")
        raise Http404()
    if order.cancelled_at is not None:
        return render(request, "signup/cancelled.html", {"application": application})
    obligations = list(order.paymentobligation_set.all())
    if not obligations or any(not o.is_fully_paid for o in obligations):
        return render(request, "signup/open.html", {"application": application})
    return render(request, "signup/return.html")
