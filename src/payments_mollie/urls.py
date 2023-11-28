from django.urls import path

from payments_mollie.views import initiate_ideal, mollie_return, mollie_webhook


app_name = "payments_mollie"

urlpatterns = [
    path("<slug:issuer_id>/<slug:payable_id>", initiate_ideal, name="ideal"),
    path("return/<slug:payable_id>", mollie_return, name="return"),
    path("cancel/<slug:payable_id>", mollie_return, name="cancel"),
    path("webhook/", mollie_webhook, name="webhook")
]
