import logging

from django.http import HttpResponseRedirect
from django.urls import reverse

from symfexit.payments.mollie.admin import MollieSettingsInline
from symfexit.payments.mollie.models import MollieCustomer, MolliePayment, MollieSettings
from symfexit.payments.registry import PaymentProcessor, PaymentProcessorInstance, payments_registry

logger = logging.getLogger(__name__)

MOLLIE_NAME = "mollie"


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
    customer = client.customers.create({"name": name, "email": email})
    return customer["id"]


def _has_valid_mandate(client, mollie_customer_id):
    mandates = client.customer_mandates.with_parent_id(mollie_customer_id).list()
    return any(m["status"] == "valid" for m in mandates["_embedded"]["mandates"])


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
    def __init__(self, mollie_settings):
        self.mollie_settings = mollie_settings

    def start_payment_flow(self, request, obligation, return_url):
        client = self.mollie_settings.get_mollie_client()

        webhook_url = request.build_absolute_uri(reverse("payments_mollie:webhook"))
        absolute_return_url = request.build_absolute_uri(return_url)

        amount_str = f"{obligation.amount_euros:.2f}"
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
            mollie_customer = _get_or_create_mollie_customer(client, user)
            customer_id = mollie_customer.mollie_customer_id
        else:
            # Signup flow — create Mollie customer from billing address
            billing = obligation.ordered_for_billing_address
            customer_id = _create_mollie_customer(client, billing.name, billing.email)

        payment_data["customerId"] = customer_id

        if user is not None and _has_valid_mandate(client, customer_id):
            # Recurring payment — charge directly, no checkout needed
            payment_data["sequenceType"] = "recurring"
            payment = client.payments.create(payment_data)

            MolliePayment.objects.create(
                obligation=obligation,
                mollie_payment_id=payment["id"],
                mollie_customer_id=customer_id,
            )

            return HttpResponseRedirect(absolute_return_url)

        # First payment — user goes through checkout to create mandate
        payment_data["sequenceType"] = "first"
        payment_data["redirectUrl"] = absolute_return_url

        payment = client.payments.create(payment_data)

        MolliePayment.objects.create(
            obligation=obligation,
            mollie_payment_id=payment["id"],
            mollie_customer_id=customer_id,
        )

        return HttpResponseRedirect(payment.checkout_url)

    def charge_obligation(self, obligation):
        user = obligation.order.ordered_for

        try:
            mollie_customer = MollieCustomer.objects.get(user=user)
        except MollieCustomer.DoesNotExist:
            return False

        client = self.mollie_settings.get_mollie_client()

        if not _has_valid_mandate(client, mollie_customer.mollie_customer_id):
            return False

        webhook_path = reverse("payments_mollie:webhook")
        webhook_url = self.mollie_settings.webhook_base_url.rstrip("/") + webhook_path

        amount_str = f"{obligation.amount_euros:.2f}"
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

        return True
