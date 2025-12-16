from django.urls import path

from symfexit.events.views import Events, signup_event, unsign_event

app_name = "events"

urlpatterns = [
    path("events/", Events.as_view(), name="events"),
    path("events/signup/<int:event_id>/", signup_event, name="signup_event"),
    path("events/unsign/<int:event_id>/", unsign_event, name="unsign_event"),
]
