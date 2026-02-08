from django.db import models


class MollieSettings(models.Model):
    payment_provider = models.OneToOneField(
        "payments.PaymentProvider",
        on_delete=models.CASCADE,
        related_name="mollie_settings",
    )
    api_key = models.CharField(max_length=255, blank=True)
    test_api_key = models.CharField(max_length=255, blank=True)
    live_mode = models.BooleanField(default=False)

    def __str__(self):
        return f"Mollie settings (live mode: {self.live_mode})"
