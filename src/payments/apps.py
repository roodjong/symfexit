from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self):
        from payments.registry import payments_registry
        self.module.autodiscover()
        payments_registry.initialize()
