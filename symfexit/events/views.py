from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views.generic import ListView
from django.utils.timezone import now

from symfexit.members.models import User
from symfexit.events.models import Event

# Create your views here.


class Events(LoginRequiredMixin, ListView):
    template_name = "events/events.html"
    model = Event
    context_object_name = "events"

    def get_queryset(self):
        return Event.objects.filter(event_date__gte=now()).order_by("event_date")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.member_type != User.MemberType.MEMBER:
            return redirect("members:memberdata")
        return super().dispatch(request, args, kwargs)
