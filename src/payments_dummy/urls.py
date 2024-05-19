from django.urls import path

from payments_dummy.views import initiate_dummy

app_name = "payments_dummy"

urlpatterns = [
    path("pay/<slug:order_id>", initiate_dummy, name="subscription"),
]
