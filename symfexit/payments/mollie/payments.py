import logging

from django.conf import settings
from django.shortcuts import render

from symfexit.payments import PaymentProcessor
from symfexit.payments.models import Subscription
from symfexit.payments.registry import payments_registry

try:
    from mollie.api.client import Client
except ImportError:
    Client = None

logger = logging.getLogger(__name__)

MOLLIE_NAME = "mollie"


@payments_registry.register(name=MOLLIE_NAME, priority=100)
class MollieProcessor(PaymentProcessor):
    def __init__(self):
        self.client = None
        super().__init__()

    @classmethod
    def get_instance(cls):
        return payments_registry.get(MOLLIE_NAME)

    def initialize(self):
        if Client is None:
            return False
        if settings.MOLLIE_API_KEY is None:
            logger.warning("MOLLIE_API_KEY is not set, disabling mollie payments")
            return False
        client = Client()
        client.set_api_key(settings.MOLLIE_API_KEY)
        self.client = client

    def is_available(self):
        return self.client is not None and self.client.methods.list().count > 0

    def start_subscription_flow(self, request, subscription: Subscription, return_url):
        order = subscription.new_order(initial=True, return_url=return_url)
        order.payment_method = MOLLIE_NAME
        order.save()
        payment_methods = self.client.methods.list(
            sequenceType="first",
            locale="nl_NL",
            amount={"value": f"{order.price / 100:.02f}", "currency": "EUR"},
            billingCountry="NL",
            include="issuers",
        )

        return render(
            request,
            "payments_mollie/select_method.html",
            {
                "payment_methods": payment_methods["_embedded"]["methods"],
                "order": order,
                "euro_price": format(order.price / 100, ".2f"),
            },
        )
