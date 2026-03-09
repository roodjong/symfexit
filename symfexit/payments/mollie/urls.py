from django.urls import path

from symfexit.payments.mollie.views import mollie_webhook

app_name = "payments_mollie"

urlpatterns = [
    path("webhook/", mollie_webhook, name="webhook"),
]
