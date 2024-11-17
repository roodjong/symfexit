from django.utils.module_loading import autodiscover_modules

from symfexit.payments.registry import PaymentProcessor, payments_registry

__all__ = ["PaymentProcessor"]


def autodiscover():
    autodiscover_modules("payments", register_to=payments_registry)
