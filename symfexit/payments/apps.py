from datetime import timedelta

from django.apps import AppConfig
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def create_default_providers(sender, **kwargs):
    from symfexit.payments.models import PaymentProvider  # noqa: PLC0415
    from symfexit.payments.registry import payments_registry  # noqa: PLC0415

    for name, processor in payments_registry:
        if not processor.can_install():
            continue
        if PaymentProvider.objects.filter(type=name).exists():
            continue
        default_account = processor.get_default_credit_account()
        kwargs = {"name": processor.name(), "type": name}
        if default_account:
            kwargs["credit_to_account"] = default_account
        PaymentProvider.objects.create(**kwargs)


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "symfexit.payments"
    verbose_name = _("Payments")

    def ready(self):
        from django.db.models.signals import post_migrate  # noqa: PLC0415

        from symfexit.payments.registry import payments_registry  # noqa: PLC0415

        self.module.autodiscover()
        payments_registry.initialize()
        post_migrate.connect(create_default_providers, sender=self)

    def get_admin_warnings(self, request):
        from symfexit.worker.models import Task  # noqa: PLC0415

        latest = (
            Task.objects.filter(name="gen_obligations", status=Task.Status.COMPLETED)
            .order_by("-completed_at")
            .first()
        )
        if latest is None or latest.completed_at < timezone.now() - timedelta(days=7):
            return [
                _(
                    "Payment obligations haven't been generated recently. "
                    "Make sure the generate_obligations command is scheduled."
                )
            ]

        return []

    def get_app_admin_urls(self, admin_site):
        from symfexit.payments.admin import (  # noqa: PLC0415
            get_or_create_billing_address,
            load_product_info,
        )

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
                name="get_or_create_billing_address_base",
            ),
            path(
                "api/get-or-create-billing-address/<int:user_id>",
                admin_site.admin_view(get_or_create_billing_address),
                name="get_or_create_billing_address",
            ),
        ]
