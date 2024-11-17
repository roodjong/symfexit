from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.payments"
    verbose_name = _("Payments")

    def ready(self):
        from symfexit.payments.registry import payments_registry

        self.module.autodiscover()
        payments_registry.initialize()
