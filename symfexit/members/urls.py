from django.urls import path

from symfexit.members.views import Logout, MemberData, payment_start

app_name = "members"

urlpatterns = [
    path("gegevens/", MemberData.as_view(), name="memberdata"),
    path("payment/start", payment_start, name="payment-start"),
    path("logout/", Logout.as_view(), name="logout"),
]
