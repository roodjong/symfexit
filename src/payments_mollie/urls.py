from django.urls import path

from payments_mollie.views import (
    initiate_ideal,
    mollie_cancel,
    mollie_return,
    mollie_webhook,
)

app_name = "payments_mollie"

urlpatterns = [
    path("start/<slug:issuer_id>/<slug:order_id>", initiate_ideal, name="ideal"),
    path("return/<slug:order_id>", mollie_return, name="return"),
    path("cancel/<slug:order_id>", mollie_cancel, name="cancel"),
    path("webhook/", mollie_webhook, name="webhook"),
]
