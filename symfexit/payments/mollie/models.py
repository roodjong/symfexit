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
    payment_description = models.CharField(
        max_length=255,
        default="{product_name} - {member_number}",
        help_text="Template for payment description. Available variables: {order_id}, {product_name}, {amount}, {member_number}",
    )

    def __str__(self):
        return f"Mollie settings (live mode: {self.live_mode})"

    def format_description(self, obligation):
        user = obligation.order.ordered_for
        member_number = str(user.member_identifier) if user else ""
        return self.payment_description.format(
            order_id=obligation.order.id,
            product_name=obligation.order.product_name,
            amount=f"{obligation.amount_euros:.2f}",
            member_number=member_number,
            first_name=user.first_name if user else "",
            last_name=user.last_name if user else "",
            full_name=user.get_full_name() if user else "",
        )

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
