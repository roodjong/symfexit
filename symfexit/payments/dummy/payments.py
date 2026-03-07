from django.conf import settings
from django.shortcuts import render

from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.registry import PaymentProcessor, PaymentProcessorInstance, payments_registry

DUMMY_NAME = "dummy"


@payments_registry.register(name=DUMMY_NAME, priority=0)
class DummyProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def can_install(self):
        return getattr(settings, "SYMFEXIT_ENV", "") == "development"

    def is_available(self):
        return bool(settings.DEBUG)

    def get_instance(self, provider):
        return DummyProcessorInstance()


class DummyProcessorInstance(PaymentProcessorInstance):
    def start_payment_flow(self, request, obligation, return_url):
        request.session[f"dummy_return_url_{obligation.id}"] = return_url
        return render(
            request,
            "payments_dummy/dummy_pay.html",
            {"obligation": obligation, "form": FakePayForm()},
        )
