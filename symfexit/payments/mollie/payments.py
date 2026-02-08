# from symfexit.payments.dummy.forms import FakePayForm
# from symfexit.payments.models import Subscription

from symfexit.payments.mollie.admin import MollieSettingsInline
from symfexit.payments.registry import PaymentProcessor, payments_registry

MOLLIE_NAME = "mollie"


@payments_registry.register(name=MOLLIE_NAME, priority=100)
class MollieProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def description(self):
        return "Mollie"

    def is_available(self):
        return True

    def get_settings_inline(self):
        return MollieSettingsInline
