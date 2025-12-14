from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.views.generic import ListView

from symfexit.events.models import Event
from symfexit.members.models import User

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


@login_required
def signup_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # Only members can sign up
    if request.user.member_type != request.user.MemberType.MEMBER:
        return redirect("members:memberdata")

    event.attendees.add(request.user)
    return redirect(reverse("events:events"))


@login_required
def unsign_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # Only members can remove themselves
    if request.user.member_type != request.user.MemberType.MEMBER:
        return redirect("members:memberdata")

    event.attendees.remove(request.user)
    return redirect(reverse("events:events"))
