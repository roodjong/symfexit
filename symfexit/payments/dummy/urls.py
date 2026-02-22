from django.urls import path

from symfexit.payments.dummy.views import initiate_dummy

app_name = "payments_dummy"

urlpatterns = [
    path("pay/<int:obligation_id>", initiate_dummy, name="pay"),
]
