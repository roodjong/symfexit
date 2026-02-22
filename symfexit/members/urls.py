from django.urls import path

from symfexit.members.views import Logout, MemberData, MembershipSelection, payment_start

app_name = "members"

urlpatterns = [
    path("gegevens/", MemberData.as_view(), name="memberdata"),
    path("membership/", MembershipSelection.as_view(), name="membership-selection"),
    path("payment/start", payment_start, name="payment-start"),
    path("logout/", Logout.as_view(), name="logout"),
]
