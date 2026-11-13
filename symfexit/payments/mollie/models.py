from functools import cache

import requests
from django.conf import settings
from django.db import models
from mollie.api.client import Client
from urllib3.util import Retry


class _Client(Client):
    """Mollie client that also retries rate-limited (429) requests.

    A 429 means Mollie rejected the request without processing it, so retrying
    is safe for POSTs too. Retry-After is honoured; once retries run out the
    429 response is returned and the library raises a ResponseError as usual.
    """

    def _setup_retry(self) -> None:
        retry = Retry(
            connect=self.retry,
            read=0,
            status=5,
            status_forcelist=[429],
            allowed_methods=None,
            backoff_factor=1,
            raise_on_status=False,
        )
        self._client.mount("https://", requests.adapters.HTTPAdapter(max_retries=retry))


@cache
def _get_client(api_key: str) -> Client:
    # One client per API key so connections are pooled and reused. A Client
    # holds a reference cycle (its resources point back at it), so throwaway
    # clients are only freed by the cyclic GC and leak their sockets until then.
    client = _Client()
    client.set_api_key(api_key)
    return client


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
        return _get_client(self.api_key if self.live_mode else self.test_api_key)


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
    # Statuses where Mollie may still collect the money. A recurring SEPA
    # direct debit stays `pending` for days before it becomes `paid`.
    IN_FLIGHT_STATUSES = ("open", "pending", "authorized")

    obligation = models.ForeignKey(
        "payments.PaymentObligation",
        on_delete=models.CASCADE,
        related_name="mollie_payments",
    )
    mollie_payment_id = models.CharField(max_length=255, unique=True, db_index=True)
    mollie_customer_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, default="open")
    processed_at = models.DateTimeField(null=True, blank=True)
    # The Payments its receipt was booked as: the part applied to the
    # obligation and/or the surplus that went to member credit.
    payments = models.ManyToManyField(
        "payments.Payment", blank=True, related_name="mollie_payments"
    )

    def __str__(self):
        return f"Mollie payment {self.mollie_payment_id} ({self.status})"


class MollieReversal(models.Model):
    """A refund or chargeback Mollie reported on one of our payments.

    One row per Mollie refund/chargeback id, so each is booked only once.
    """

    class Kind(models.TextChoices):
        REFUND = "refund", "Refund"
        CHARGEBACK = "chargeback", "Chargeback"

    # Refund statuses after which no money goes back to the member.
    REFUND_UNSUCCESSFUL_STATUSES = ("failed", "canceled")

    mollie_payment = models.ForeignKey(
        MolliePayment, on_delete=models.CASCADE, related_name="reversals"
    )
    mollie_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=20, choices=Kind)
    amount_cents = models.IntegerField()
    # Refund status from Mollie; empty for chargebacks.
    status = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # When it was booked in the ledger. A refund is booked once Mollie reports
    # it `refunded`, a chargeback as soon as it appears.
    processed_at = models.DateTimeField(null=True, blank=True)
    # For a refund started from the admin: the Payment it refunds. Empty for
    # chargebacks and dashboard refunds, which undo the whole receipt.
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # The ledger entries it was booked as.
    payment_reversals = models.ManyToManyField(
        "payments.PaymentReversal", blank=True, related_name="mollie_reversals"
    )
    # A chargeback the bank later reversed: the money came back to us.
    chargeback_reversed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Mollie {self.kind} {self.mollie_id}"
