import logging

from django.shortcuts import render
from django.template.loader import get_template
from payments import PaymentProcessor
from payments.models import Payable
from payments.registry import payments_registry
from symfexit import settings

try:
    from mollie.api.client import Client
except ImportError:
    Client = None

logger = logging.getLogger(__name__)


@payments_registry.register(name="mollie", priority=10)
class MollieProcessor(PaymentProcessor):
    def __init__(self):
        self.client = None
        super().__init__()

    @classmethod
    def get_instance(cls):
        return payments_registry.get("mollie")

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

    def render_payment_start(self, payable: Payable):
        payment_methods = self.client.methods.list(
            sequenceType="first",
            locale="nl_NL",
            amount={"value": "{:.02f}".format(payable.price / 100), "currency": "EUR"},
            billingCountry="NL",
            include="issuers",
        )
        print("payment_methods", payment_methods)
        t = get_template("payments_mollie/select_method.html")
        return t.render(
            {
                "payment_methods": payment_methods["_embedded"]["methods"],
                "payable": payable,
            }
        )
