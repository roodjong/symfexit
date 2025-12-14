from django.urls import path

from symfexit.events.views import Events

app_name = "events"

urlpatterns = [
    path("events/", Events.as_view(), name="events"),
]
