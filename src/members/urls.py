from django.urls import path

from members.views import Logout, MemberData

app_name = "members"

urlpatterns = [
    path("gegevens/", MemberData.as_view(), name="memberdata"),
    path("logout/", Logout.as_view(), name="logout")
]
