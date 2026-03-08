import abc
import bisect
import logging

import symfexit

logger = logging.getLogger(__name__)

__all__ = ["payments_registry", "PaymentsRegistry", "PaymentProcessor"]


class PaymentsRegistry:
    def __init__(self):
        self._registry: list[tuple[int, PaymentProcessor]] = []
        self._names = {}

    def register(self, *, name, priority=0):
        def _register(cls):
            if not issubclass(cls, PaymentProcessor):
                raise ValueError("Registered class must be a subclass of PaymentProcessor")
            instance = cls()
            bisect.insort_right(self._registry, (priority, instance), key=lambda x: x[0])
            self._names[name] = instance
            # logging.info(f"Registered payment processor {name} with priority {priority}")
            return cls

        return _register

    def get(self, name):
        return self._names.get(name)

    def get_main(self):
        for _, processor in reversed(self._registry):
            try:
                if processor.is_available():
                    logging.info(f"Using payment processor {processor.name()}")
                    return processor
            except Exception as e:
                logging.error(f"Error checking availability of processor {processor.name()}: {e}")
                pass
        raise RuntimeError("No available payment processor found")

    def get_default_instance(self):
        from symfexit.payments.models import PaymentProvider  # noqa: PLC0415

        provider = PaymentProvider.objects.filter(default=True).first()
        if not provider:
            raise RuntimeError("No default payment provider configured")
        processor = self.get(provider.type)
        if not processor:
            raise RuntimeError(f"Payment processor {provider.type} not found in registry")
        return processor.get_instance(provider)

    def initialize(self):
        for _, processor in self._registry:
            processor.initialize()

    def __iter__(self):
        return iter(self._names.items())


payments_registry = PaymentsRegistry()


class PaymentProcessor(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def initialize(self): ...

    def name(self):
        return self.__class__.__name__

    def allows_manual_payments(self) -> bool:
        """Returns whether this payment processor allows manual payments (e.g. for offline payment methods)."""
        return False

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Returns whether this payment processor is available."""
        ...

    @abc.abstractmethod
    def can_install(self) -> bool:
        """Returns whether this payment processor can be installed in this environment."""
        ...

    def get_default_credit_account(self) -> "symfexit.payments.models.Account | None":
        """Returns the default credit-to account for this processor, or None for the bank account."""
        return None

    def get_settings_inline(self) -> type | None:
        """Returns an optional admin inline for the settings of this payment processor."""
        return None

    @abc.abstractmethod
    def get_instance(self, provider: "symfexit.payments.models.PaymentProvider"):
        """Returns an instance of this payment processor for the given provider."""
        ...


class PaymentProcessorInstance(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def start_payment_flow(self, request, obligation, return_url):
        """Starts the payment flow for the given payment obligation.

        Should return an HttpResponse (either a redirect or a rendered template).
        """
        ...
