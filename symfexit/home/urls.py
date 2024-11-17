from django.urls import path

from symfexit.home.views import Home

app_name = "home"

urlpatterns = [
    path("", Home.as_view(), name="home"),
    path("admin/send/<int:pk>/", Home.as_view(), name="admin-send"),
]
