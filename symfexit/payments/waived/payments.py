from symfexit.payments.registry import PaymentProcessor, payments_registry

WAIVED_NAME = "waived"


@payments_registry.register(name=WAIVED_NAME, priority=0)
class WaivedProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def can_install(self):
        return True

    def allows_manual_payments(self):
        return True

    def is_available(self):
        return False

    def get_default_credit_account(self):
        from symfexit.payments.models import Account  # noqa: PLC0415

        account, _ = Account.get_waived_account()
        return account

    def get_instance(self, provider):
        raise NotImplementedError("Waived payments do not support an online payment flow")
