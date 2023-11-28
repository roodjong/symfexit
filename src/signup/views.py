from base64 import urlsafe_b64decode, urlsafe_b64encode
from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views.generic import FormView
from payments.models import Payable

from signup.forms import SignupForm
from signup.models import MembershipApplication

# Create your views here.


class MemberSignup(FormView):
    template_name = "signup/signup.html"
    success_url = reverse_lazy("signup:payment")
    form_class = SignupForm

    def form_valid(self, form):
        logout(self.request)
        application = form.save()
        return HttpResponseRedirect(
            reverse("signup:payment", args=[application.eid])
        )


def member_signup_pay(request, application_id):
    application = MembershipApplication.get_or_404(application_id)
    return render(
        request,
        "signup/payment.html",
        {
            "application": application,
            "payment_amount_euros": "{:.02f}".format(application.payment_amount / 100),
        },
    )

def member_signup_pay_retry(request, application_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    application = MembershipApplication.get_or_404(application_id)
    application.new_payable()
    return HttpResponseRedirect(
        reverse("signup:payment", args=[application.eid])
    )

def return_view(request, application_id):
    application = MembershipApplication.get_or_404(application_id)
    if application.payable.payment_status == Payable.Status.CANCELLED:
        return render(request, "signup/cancelled.html", {"application": application})
    return render(request, "signup/return.html")
