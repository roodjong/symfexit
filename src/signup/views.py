import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode

from django.conf import settings
from django.contrib.auth import logout
from django.http import (Http404, HttpResponseNotAllowed, HttpResponseNotFound,
                         HttpResponseRedirect)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views.generic import FormView

from payments.models import Order
from payments.registry import payments_registry
from signup.forms import SignupForm
from signup.models import MembershipApplication

logger = logging.getLogger(__name__)


class MemberSignup(FormView):
    template_name = "signup/signup.html"
    success_url = reverse_lazy("signup:payment")
    form_class = SignupForm

    def form_valid(self, form):
        logout(self.request)
        application = form.save()
        return HttpResponseRedirect(reverse("signup:payment", args=[application.eid]))


def member_signup_pay(request, application_id):
    provider = payments_registry.get_main()
    application = MembershipApplication.get_or_404(application_id)
    subscription = application.get_or_create_subscription()
    return provider.start_subscription_flow(
        request, subscription, reverse("signup:return", args=[application.eid])
    )


def member_signup_pay_retry(request, application_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    application = MembershipApplication.get_or_404(application_id)
    provider = payments_registry.get_main()
    subscription = application.get_or_create_subscription()
    return provider.start_subscription_flow(
        request, subscription, reverse("signup:return", args=[application.eid])
    )


def return_view(request, application_id):
    application = MembershipApplication.get_or_404(application_id)
    order = application._order
    if order is None:
        logger.warning(f"Order not found for application {application_id}")
        raise Http404()
    if order.payment_status == Order.Status.CANCELLED:
        return render(request, "signup/cancelled.html", {"application": application})
    return render(request, "signup/return.html")
