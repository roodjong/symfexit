from django.urls import path

from symfexit.events.views import EventsOverview

app_name = "events"

urlpatterns = [
    path("evenementen/", EventsOverview.as_view(), name="overview"),
]
