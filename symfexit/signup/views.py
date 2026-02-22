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
from symfexit.signup.forms import CUSTOM_TIER_VALUE, SignupForm
from symfexit.signup.models import MembershipApplication

logger = logging.getLogger(__name__)


class MemberSignup(FormView):
    template_name = "signup/signup.html"
    success_url = reverse_lazy("signup:payment")
    form_class = SignupForm

    def dispatch(self, *args, initialgroup: str | None = None, **kwargs):
        self.initialgroup = initialgroup
        return super().dispatch(*args, **kwargs)

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
    provider = payments_registry.get_main()
    application = MembershipApplication.get_or_404(application_id)
    order = application.get_or_create_order()
    return provider.start_payment_flow(
        request, order, reverse("signup:return", args=[application.eid])
    )


def member_signup_pay_retry(request, application_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    application = MembershipApplication.get_or_404(application_id)
    provider = payments_registry.get_main()
    order = application.get_or_create_order()
    return provider.start_payment_flow(
        request, order, reverse("signup:return", args=[application.eid])
    )


def return_view(request, application_id):
    application = MembershipApplication.get_or_404(application_id)
    order = application._order
    if order is None:
        logger.warning(f"Order not found for application {application_id}")
        raise Http404()
    if not order.payment_set.exists():
        return render(request, "signup/cancelled.html", {"application": application})
    return render(request, "signup/return.html")
