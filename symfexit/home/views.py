from constance import config
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from symfexit.home.models import HomePage
from symfexit.members.models import User

# Create your views here.


class Home(LoginRequiredMixin, TemplateView):
    template_name = "home/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hp = HomePage.objects.filter(id=config.HOMEPAGE_CURRENT)
        if hp:
            context["homepage"] = hp[0]
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.member_type != User.MemberType.MEMBER:
            return redirect("members:memberdata")
        return super().dispatch(request, args, kwargs)
