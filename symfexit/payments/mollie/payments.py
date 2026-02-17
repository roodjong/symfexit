from symfexit.payments.mollie.admin import MollieSettingsInline
from symfexit.payments.mollie.models import MollieSettings
from symfexit.payments.registry import PaymentProcessor, payments_registry

MOLLIE_NAME = "mollie"


@payments_registry.register(name=MOLLIE_NAME, priority=100)
class MollieProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def description(self):
        return "Mollie"

    def is_available(self):
        return MollieSettings.objects.filter(api_key__gt="").exists()

    def get_settings_inline(self):
        return MollieSettingsInline
