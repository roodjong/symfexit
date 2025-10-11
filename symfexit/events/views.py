from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import TemplateView

from symfexit.events.models import Event


class EventsOverview(LoginRequiredMixin, TemplateView):
    template_name = "overview.html"

    def get(self, request, *args, **kwargs):
        cutoff = datetime.now() - timedelta(hours=1)

        events = Event.objects.filter(
            (Q(organised_by__in=request.user.groups.all()) | Q(organised_by=None))
            & Q(ends_at__gt=cutoff)
        ).order_by("starts_at")
        return render(
            request,
            self.template_name,
            {
                "events": events,
            },
        )
