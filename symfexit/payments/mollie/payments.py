import logging
from datetime import timedelta

from django.db.models import Q, Sum
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from mollie.api.client import Client
from mollie.api.objects.customer import Customer as MollieApiCustomer

from symfexit.payments.mollie.admin import MollieSettingsInline
from symfexit.payments.mollie.models import (
    MollieCustomer,
    MolliePayment,
    MollieReversal,
    MollieSettings,
)
from symfexit.payments.mollie.views import _refresh_from_mollie, build_pending_url, sync_refund
from symfexit.payments.registry import PaymentProcessor, PaymentProcessorInstance, payments_registry
from symfexit.worker import logger as worker_logger

logger = logging.getLogger(__name__)

MOLLIE_NAME = "mollie"

# Amount of the "first" payment that registers a new mandate when the user
# changes their bank account. Kept at one cent so the regular subscription
# charging (charge_obligations) simply continues against the new mandate;
# record_receipt applies the cent toward the user's obligation.
BANK_ACCOUNT_VERIFICATION_CENTS = 1

# How far back to look for refunds and chargebacks. A SEPA direct debit can be
# charged back up to 13 months later when the member says it was unauthorised.
REVERSAL_LOOKBACK = timedelta(days=400)


def _get_or_create_mollie_customer(client, user):
    try:
        return MollieCustomer.objects.get(user=user)
    except MollieCustomer.DoesNotExist:
        customer = client.customers.create({"name": user.get_full_name(), "email": user.email})
        return MollieCustomer.objects.create(
            user=user,
            mollie_customer_id=customer["id"],
        )


def _create_mollie_customer(client, name, email):
    return client.customers.create({"name": name, "email": email})


def _log_debug_changepaymentstate_url(payment):
    """Surface Mollie's test-mode `changePaymentState` link.

    Recurring payments have no checkout URL — the customer isn't involved — so in
    test mode Mollie returns this link instead, which lets you set the final state
    of the payment (and afterwards create a refund or chargeback for it).
    Absent in live mode."""
    url = payment.changepaymentstate_url
    if url:
        logger.info("Mollie payment %s: set its state in test mode at %s", payment["id"], url)


def _has_valid_mandate(mollie_customer: MollieApiCustomer):
    mandates = mollie_customer.mandates.list()
    return any(m["status"] == "valid" for m in mandates["_embedded"]["mandates"])


# Metadata flag on the "first" payment of a bank account change, so the
# webhook knows to revoke the old mandates once the new one exists.
BANK_ACCOUNT_CHANGE_METADATA_KEY = "bank_account_change"


def revoke_other_mandates(mollie_customer: MollieApiCustomer, keep_mandate_id: str | None):
    """Revoke all valid or pending mandates except `keep_mandate_id`, so the
    new mandate becomes the only one used for recurring charges. With None,
    revokes them all."""
    mandates = mollie_customer.mandates.list()
    for mandate in mandates["_embedded"]["mandates"]:
        if mandate["status"] == "invalid" or mandate["id"] == keep_mandate_id:
            continue
        try:
            mollie_customer.mandates.delete(mandate["id"])
        except Exception:
            logger.warning(
                "Failed to revoke mandate %s for Mollie customer %s",
                mandate["id"],
                mollie_customer.id,
                exc_info=True,
            )


def _iter_since(resource, since):
    """Walk a Mollie list endpoint (newest first) back to `since`."""
    page = resource.list(limit=250)
    while True:
        items = list(page)
        for item in items:
            if parse_datetime(item["createdAt"]) < since:
                return
            yield item
        if not items or not page.has_next():
            return
        page = page.get_next()


def _needs_sync(item, reversal: MollieReversal | None) -> bool:
    if reversal is None:
        return True
    if reversal.kind == MollieReversal.Kind.CHARGEBACK:
        return reversal.processed_at is None or bool(
            item.get("reversedAt") and reversal.chargeback_reversed_at is None
        )
    return reversal.processed_at is None and reversal.status != item["status"]


def link_mollie_customer_to_user(order, user):
    """Link a Mollie customer (created during signup) to a newly created user.

    Finds the MolliePayment for the order that has a mollie_customer_id
    and creates a MollieCustomer record linking it to the user.
    """
    mollie_payment = (
        MolliePayment.objects.filter(
            obligation__order=order,
            mollie_customer_id__gt="",
        )
        .order_by("-created_at")
        .first()
    )
    if mollie_payment is None:
        return None

    if MollieCustomer.objects.filter(user=user).exists():
        return MollieCustomer.objects.get(user=user)

    return MollieCustomer.objects.create(
        user=user,
        mollie_customer_id=mollie_payment.mollie_customer_id,
    )


@payments_registry.register(name=MOLLIE_NAME, priority=100)
class MollieProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def name(self):
        return "Mollie"

    def is_available(self):
        return MollieSettings.objects.filter(api_key__gt="").exists()

    def can_install(self):
        return True

    def get_settings_inline(self):
        return MollieSettingsInline

    def get_instance(self, provider):
        return MollieProcessorInstance(provider.mollie_settings)


class MollieProcessorInstance(PaymentProcessorInstance):
    def __init__(self, mollie_settings: MollieSettings):
        self.mollie_settings = mollie_settings

    def _build_webhook_url(self, request):
        """Prefer the configured webhook base URL (e.g. an ngrok tunnel in
        development) over the URL of the incoming request."""
        webhook_path = reverse("payments_mollie:webhook")
        if self.mollie_settings.webhook_base_url:
            return self.mollie_settings.webhook_base_url.rstrip("/") + webhook_path
        return request.build_absolute_uri(webhook_path)

    def start_payment_flow(self, request, obligation, return_url):
        # Already paid (e.g. fully covered by member credit) — nothing for Mollie to charge.
        if obligation.is_fully_paid:
            return HttpResponseRedirect(request.build_absolute_uri(return_url))

        client: Client = self.mollie_settings.get_mollie_client()

        webhook_url = self._build_webhook_url(request)
        pending_url = build_pending_url(request, obligation, return_url)

        amount_str = f"{obligation.outstanding_cents / 100:.2f}"
        description = self.mollie_settings.format_description(obligation)

        payment_data = {
            "amount": {
                "currency": "EUR",
                "value": amount_str,
            },
            "description": description,
            "webhookUrl": webhook_url,
            "metadata": {
                "obligation_id": str(obligation.id),
                "order_id": str(obligation.order.id),
            },
        }

        user = obligation.order.ordered_for

        if user is not None:
            symfexit_customer = _get_or_create_mollie_customer(client, user)
            customer_id = symfexit_customer.mollie_customer_id
            mollie_customer = client.customers.get(customer_id)
        else:
            # Signup flow — create Mollie customer from billing address
            billing = obligation.ordered_for_billing_address
            mollie_customer = _create_mollie_customer(client, billing.name, billing.email)
            customer_id = mollie_customer.id

        payment_data["customerId"] = customer_id

        if user is not None and _has_valid_mandate(mollie_customer):
            # Recurring payment — charge directly, no checkout needed
            payment_data["sequenceType"] = "recurring"
            payment = client.payments.create(payment_data)

            MolliePayment.objects.create(
                obligation=obligation,
                mollie_payment_id=payment["id"],
                mollie_customer_id=customer_id,
            )

            return HttpResponseRedirect(pending_url)

        # First payment — user goes through checkout to create mandate
        payment_data["sequenceType"] = "first"
        payment_data["redirectUrl"] = pending_url

        payment = client.payments.create(payment_data)

        MolliePayment.objects.create(
            obligation=obligation,
            mollie_payment_id=payment["id"],
            mollie_customer_id=customer_id,
        )

        return HttpResponseRedirect(payment.checkout_url)

    def supports_bank_account_change(self):
        return True

    def start_bank_account_change_flow(self, request, obligation, return_url):
        """Let the user register a new bank account for their recurring payments.

        Sends the user through a new "first" checkout payment of one cent,
        which creates a fresh mandate from whichever account the user pays
        with. The existing mandates are only revoked once that payment is paid
        (see the webhook), so an abandoned or expired checkout leaves the
        current mandate in place. The regular subscription charging then
        continues against the new mandate.
        """
        client: Client = self.mollie_settings.get_mollie_client()

        user = obligation.order.ordered_for
        symfexit_customer = _get_or_create_mollie_customer(client, user)
        customer_id = symfexit_customer.mollie_customer_id

        webhook_url = self._build_webhook_url(request)
        pending_url = build_pending_url(request, obligation, return_url)

        amount_cents = BANK_ACCOUNT_VERIFICATION_CENTS

        payment = client.payments.create(
            {
                "amount": {
                    "currency": "EUR",
                    "value": f"{amount_cents / 100:.2f}",
                },
                "description": self.mollie_settings.format_description(obligation),
                "webhookUrl": webhook_url,
                "redirectUrl": pending_url,
                "sequenceType": "first",
                "customerId": customer_id,
                "metadata": {
                    "obligation_id": str(obligation.id),
                    "order_id": str(obligation.order.id),
                    BANK_ACCOUNT_CHANGE_METADATA_KEY: True,
                },
            }
        )

        MolliePayment.objects.create(
            obligation=obligation,
            mollie_payment_id=payment["id"],
            mollie_customer_id=customer_id,
        )

        return HttpResponseRedirect(payment.checkout_url)

    def refresh_payments(self):
        # Our status goes stale when a webhook never arrives, e.g. after an
        # outage longer than Mollie's retry window. Asking Mollie directly
        # books payments that were paid (including signups whose member never
        # returned to the pending page), and unblocks obligations whose debit
        # failed so they can be charged again.
        in_flight = MolliePayment.objects.filter(
            status__in=MolliePayment.IN_FLIGHT_STATUSES,
            obligation__order__paid_using=self.mollie_settings.payment_provider,
        ).select_related("obligation__order__paid_using__mollie_settings")

        refreshed = 0
        errors = 0

        for mollie_payment in in_flight.iterator():
            try:
                _refresh_from_mollie(mollie_payment)
                refreshed += 1
            except Exception:
                errors += 1
                worker_logger.log(f"MolliePayment {mollie_payment.mollie_payment_id}: ERROR")

        worker_logger.log(f"Refreshed {refreshed} Mollie payments, {errors} errors")

        self._refresh_reversed_payments()

    def _refresh_reversed_payments(self):
        """Refunds and chargebacks land on payments that are already paid, so
        the in-flight refresh never sees them. Mollie lists both account-wide;
        refresh each of our payments that has one we haven't caught up on."""
        ours = MolliePayment.objects.filter(
            obligation__order__paid_using=self.mollie_settings.payment_provider
        )
        if not ours.exists():
            # Nothing of ours to reverse (e.g. a provider that was never set up).
            return

        client = self.mollie_settings.get_mollie_client()
        since = timezone.now() - REVERSAL_LOOKBACK
        items = [*_iter_since(client.chargebacks, since), *_iter_since(client.refunds, since)]
        known = MollieReversal.objects.in_bulk(
            [item["id"] for item in items], field_name="mollie_id"
        )
        payment_ids = {
            item["paymentId"] for item in items if _needs_sync(item, known.get(item["id"]))
        }

        payments = ours.filter(mollie_payment_id__in=payment_ids).select_related(
            "obligation__order__paid_using__mollie_settings"
        )

        refreshed = 0
        errors = 0

        for mollie_payment in payments:
            try:
                _refresh_from_mollie(mollie_payment)
                refreshed += 1
            except Exception:
                errors += 1
                worker_logger.log(f"MolliePayment {mollie_payment.mollie_payment_id}: ERROR")

        worker_logger.log(
            f"Refreshed {refreshed} refunded or charged back Mollie payments, {errors} errors"
        )

    def refundable_cents(self, payment):
        mollie_payment = payment.mollie_payments.first()
        if mollie_payment is None:
            # Not paid through Mollie, e.g. funded from member credit.
            return 0
        # Refunds Mollie hasn't completed yet that may still take this money:
        # ones for this payment, and ones for the whole Mollie payment.
        pending_cents = (
            mollie_payment.reversals.filter(
                Q(payment=payment) | Q(payment__isnull=True),
                kind=MollieReversal.Kind.REFUND,
                processed_at__isnull=True,
            )
            .exclude(status__in=MollieReversal.REFUND_UNSUCCESSFUL_STATUSES)
            .aggregate(total=Sum("amount_cents"))["total"]
            or 0
        )
        return max(0, payment.unreversed_cents - pending_cents)

    def refund(self, payment):
        amount_cents = self.refundable_cents(payment)
        if amount_cents <= 0:
            raise ValueError(f"Payment {payment.pk} has nothing left to refund through Mollie")

        mollie_payment = payment.mollie_payments.get()
        client = self.mollie_settings.get_mollie_client()
        api_payment = client.payments.get(mollie_payment.mollie_payment_id)
        refund = api_payment.refunds.create(
            {"amount": {"currency": "EUR", "value": f"{amount_cents / 100:.2f}"}}
        )
        # Books it right away if Mollie already finished it, otherwise records
        # it as pending until the webhook or refresh_payments sees it complete.
        sync_refund(mollie_payment, refund, payment=payment)

    def charge_obligation(self, obligation):
        if obligation.is_fully_paid:
            return False

        # A previous charge may still be on its way; charging again would
        # debit the member twice once both payments complete.
        if obligation.mollie_payments.filter(status__in=MolliePayment.IN_FLIGHT_STATUSES).exists():
            return False

        user = obligation.order.ordered_for

        try:
            mollie_customer = MollieCustomer.objects.get(user=user)
        except MollieCustomer.DoesNotExist:
            return False

        client = self.mollie_settings.get_mollie_client()

        api_customer = client.customers.get(mollie_customer.mollie_customer_id)
        if not _has_valid_mandate(api_customer):
            return False

        webhook_path = reverse("payments_mollie:webhook")
        webhook_url = self.mollie_settings.webhook_base_url.rstrip("/") + webhook_path

        amount_str = f"{obligation.outstanding_cents / 100:.2f}"
        description = self.mollie_settings.format_description(obligation)

        payment = client.payments.create(
            {
                "amount": {
                    "currency": "EUR",
                    "value": amount_str,
                },
                "description": description,
                "webhookUrl": webhook_url,
                "sequenceType": "recurring",
                "customerId": mollie_customer.mollie_customer_id,
                "metadata": {
                    "obligation_id": str(obligation.id),
                    "order_id": str(obligation.order.id),
                },
            }
        )

        MolliePayment.objects.create(
            obligation=obligation,
            mollie_payment_id=payment["id"],
            mollie_customer_id=mollie_customer.mollie_customer_id,
        )

        if not self.mollie_settings.live_mode:
            _log_debug_changepaymentstate_url(payment)

        return True
