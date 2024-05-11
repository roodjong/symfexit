from constance import config
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import TemplateView

from home.models import HomePage

# Create your views here.

class Home(LoginRequiredMixin, TemplateView):
    template_name = "home/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hp = HomePage.objects.filter(id=config.HOMEPAGE_CURRENT)
        if hp:
            context["homepage"] = hp[0]
        return context
