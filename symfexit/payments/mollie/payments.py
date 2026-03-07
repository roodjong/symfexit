from symfexit.payments.mollie.admin import MollieSettingsInline
from symfexit.payments.mollie.models import MollieSettings
from symfexit.payments.registry import PaymentProcessor, PaymentProcessorInstance, payments_registry

MOLLIE_NAME = "mollie"


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
        # This will be implemented in the future when we add support for Mollie payments.
        raise NotImplementedError("Mollie payment flow is not implemented yet")
