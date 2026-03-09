from django.conf import settings
from django.db import models
from mollie.api.client import Client


class MollieSettings(models.Model):
    payment_provider = models.OneToOneField(
        "payments.PaymentProvider",
        on_delete=models.CASCADE,
        related_name="mollie_settings",
    )
    api_key = models.CharField(max_length=255, blank=True)
    test_api_key = models.CharField(max_length=255, blank=True)
    live_mode = models.BooleanField(default=False)
    webhook_base_url = models.CharField(
        max_length=255,
        blank=True,
        help_text="Base URL for webhooks when no request is available (e.g. https://example.com)",
    )

    def __str__(self):
        return f"Mollie settings (live mode: {self.live_mode})"

    def get_mollie_client(self):
        client = Client()
        client.set_api_key(self.api_key if self.live_mode else self.test_api_key)
        return client


class MollieCustomer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mollie_customer",
    )
    mollie_customer_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mollie customer {self.mollie_customer_id} for {self.user}"


class MolliePayment(models.Model):
    obligation = models.ForeignKey(
        "payments.PaymentObligation",
        on_delete=models.CASCADE,
        related_name="mollie_payments",
    )
    mollie_payment_id = models.CharField(max_length=255, unique=True, db_index=True)
    mollie_customer_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="open")

    def __str__(self):
        return f"Mollie payment {self.mollie_payment_id} ({self.status})"
