from constance import config
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from symfexit.home.models import HomePage

# Create your views here.


class Home(LoginRequiredMixin, TemplateView):
    template_name = "home/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hp = HomePage.objects.filter(id=config.HOMEPAGE_CURRENT)
        if hp:
            context["homepage"] = hp[0]
        return context
