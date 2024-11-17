from django.urls import path

from symfexit.theme.views import current_style

app_name = "theme"

urlpatterns = [
    path("style/", current_style, name="current_style"),
]
