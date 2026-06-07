from django.urls import path

from symfexit.payments.mollie.views import (
    mollie_webhook,
    payment_pending,
    payment_pending_status,
)

app_name = "payments_mollie"

urlpatterns = [
    path("webhook/", mollie_webhook, name="webhook"),
    path("pending/<str:obligation_eid>/", payment_pending, name="pending"),
    path("pending/<str:obligation_eid>/status/", payment_pending_status, name="pending_status"),
]
