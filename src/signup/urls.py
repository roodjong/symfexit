from django.urls import path

from signup.views import (MemberSignup, member_signup_pay,
                          member_signup_pay_retry, return_view)

app_name = "signup"

urlpatterns = [
    path("aanmelden/", MemberSignup.as_view(), name="signup"),
    path("aanmelden/betalen/<slug:application_id>", member_signup_pay, name="payment"),
    path("aanmelden/return/<slug:application_id>", return_view, name="return"),
    path("aanmelden/retry/<slug:application_id>", member_signup_pay_retry, name="retry"),
]
