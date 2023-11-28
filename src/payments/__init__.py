from django.utils.module_loading import autodiscover_modules

from payments.registry import payments_registry, PaymentProcessor

__all__ = ["PaymentProcessor"]

def autodiscover():
    autodiscover_modules("payments", register_to=payments_registry)
