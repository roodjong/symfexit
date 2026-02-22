import abc
import bisect
import logging

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
            logging.info(f"Registered payment processor {name} with priority {priority}")
            return cls

        return _register

    def get(self, name):
        return self._names.get(name)

    def get_main(self):
        for _, processor in reversed(self._registry):
            try:
                if processor.is_available():
                    logging.info(f"Using payment processor {processor}")
                    return processor
            except Exception as e:
                logging.error(f"Error checking availability of processor {processor}: {e}")
                pass
        raise RuntimeError("No available payment processor found")

    def initialize(self):
        for _, processor in self._registry:
            processor.initialize()

    def __iter__(self):
        return reversed(self._registry)


payments_registry = PaymentsRegistry()


class PaymentProcessor(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def initialize(self):
        pass

    def description(self):
        return self.__class__.__name__

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Returns whether this payment processor is available."""
        pass

    def start_payment_flow(self, request, obligation, return_url):
        """Starts the payment flow for the given payment obligation.

        Should return an HttpResponse (either a redirect or a rendered template).
        """
        raise NotImplementedError

    def get_settings_inline(self) -> type | None:
        """Returns an optional admin inline for the settings of this payment processor."""
        return None
