from django.conf import settings
from django.shortcuts import render

from symfexit.payments import PaymentProcessor
from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.models import Subscription
from symfexit.payments.registry import payments_registry

DUMMY_NAME = "dummy"


@payments_registry.register(name=DUMMY_NAME, priority=0)
class DummyProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def is_available(self):
        return bool(settings.DEBUG)

    def start_subscription_flow(self, request, subscription: Subscription, return_url):
        order = subscription.new_order(initial=True, return_url=return_url)
        order.payment_method = DUMMY_NAME
        order.save()
        return render(
            request,
            "payments_dummy/dummy_pay.html",
            {"subscription": subscription, "order": order, "form": FakePayForm()},
        )
