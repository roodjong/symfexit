from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import TemplateView

from symfexit.members.forms import PasswordChangeForm, UserForm
from symfexit.membership.models import Membership
from symfexit.payments.models import BillingAddress


class MemberData(LoginRequiredMixin, TemplateView):
    template_name = "members/user_form.html"

    def get(self, request, *args, **kwargs):
        user_form = UserForm(instance=request.user, prefix="user_form")
        password_form = PasswordChangeForm(user=request.user, prefix="password_form")
        memberships = Membership.objects.filter(user=request.user)
        current_membership = Membership.current_for_user(request.user)
        return render(
            request,
            self.template_name,
            {
                "user_form": user_form,
                "password_form": password_form,
                "memberships": memberships,
                "current_membership": current_membership,
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


def payment_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return redirect("login")
    user = request.user
    address = BillingAddress.objects.create(
        user=user,
        name=f"{user.first_name} {user.last_name}",
        address=user.address,
        city=user.city,
        postal_code=user.postal_code,
    )
    subscription = Membership.objects.create(
        user=user,
        active_from_to=DateTimeTZRange(lower=timezone.now()),
        period_quantity=3,  # TODO: make configurable
        period_unit=Membership.PeriodUnit.MONTH,
        price_per_period="?",
        address=address,
    )
