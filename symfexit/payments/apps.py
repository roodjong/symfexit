from django.apps import AppConfig
from django.urls import path
from django.utils.translation import gettext_lazy as _


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.payments"
    verbose_name = _("Payments")

    def ready(self):
        from symfexit.payments.registry import payments_registry  # noqa: PLC0415

        self.module.autodiscover()
        payments_registry.initialize()

    def get_app_admin_urls(self, admin_site):
        from symfexit.payments.admin import load_product_info, get_or_create_billing_address  # noqa: PLC0415

        return [
            path(
                "api/load-product",
                admin_site.admin_view(load_product_info),
                name="load_product_base",
            ),
            path(
                "api/load-product/<int:product_id>",
                admin_site.admin_view(load_product_info),
                name="load_product",
            ),
            path(
                "api/get-or-create-billing-address",
                admin_site.admin_view(get_or_create_billing_address),
                name="get_or_create_billing_addres_base",
            ),
            path(
                "api/get-or-create-billing-address/<int:user_id>",
                admin_site.admin_view(get_or_create_billing_address),
                name="get_or_create_billing_addres_base",
            ),
        ]
