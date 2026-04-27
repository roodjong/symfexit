from datetime import date

from django.conf import settings
from django.core.management import BaseCommand
from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context

from symfexit.worker.registry import add_task


class Command(BaseCommand):
    help = "Queue payment obligation generation for all tenants"

    def add_arguments(self, parser):
        parser.add_argument(
            "--now",
            type=date.fromisoformat,
            default=None,
            help=(
                "For advanced usage only. Override the 'current time' used for period calculations. "
                "Format: YYYY-MM-DD. Interpreted as start-of-day in each tenant's "
                "payments timezone. Defaults to the actual current time."
            ),
        )

    def handle(self, *args, **options):
        now = options["now"]

        TenantModel = get_tenant_model()
        if settings.SINGLE_SITE:
            tenants = TenantModel.objects.all()
        else:
            tenants = TenantModel.objects.exclude(schema_name=get_public_schema_name())

        for tenant in tenants:
            self.stdout.write(f"Queuing for tenant: {tenant.name}")
            with tenant_context(tenant):
                add_task("gen_obligations", now=now)

        suffix = f" (override now={now.isoformat()})" if now else ""
        self.stdout.write(
            self.style.SUCCESS(f"Queued for {tenants.count()} tenant(s){suffix}")
        )
