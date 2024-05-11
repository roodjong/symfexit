from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from members.forms import PasswordChangeForm, UserForm
from members.models import User


class MemberData(LoginRequiredMixin, TemplateView):
    template_name = "members/user_form.html"

    def get(self, request, *args, **kwargs):
        user_form = UserForm(instance=request.user, prefix="user_form")
        password_form = PasswordChangeForm(user=request.user, prefix="password_form")
        subscriptions = request.user.subscription_set.all()
        return render(
            request,
            self.template_name,
            {
                "user_form": user_form,
                "password_form": password_form,
                "subscriptions": subscriptions,
            },
        )

    def post(self, request, *args, **kwargs):
        if "user_form" in request.POST:
            user_form = UserForm(
                request.POST, instance=request.user, prefix="user_form"
            )
            if user_form.is_valid():
                user_form.save()
                return redirect("members:memberdata")
            else:
                password_form = PasswordChangeForm(
                    user=request.user, prefix="password_form"
                )
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
