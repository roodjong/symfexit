from django.conf import settings
from django.core.management import BaseCommand
from django_tenants.utils import get_public_schema_name, get_tenant_model, tenant_context

from symfexit.worker.registry import add_task


class Command(BaseCommand):
    help = "Queue payment obligation generation for all tenants"

    def handle(self, *args, **options):
        TenantModel = get_tenant_model()
        if settings.SINGLE_SITE:
            tenants = TenantModel.objects.all()
        else:
            tenants = TenantModel.objects.exclude(schema_name=get_public_schema_name())

        for tenant in tenants:
            self.stdout.write(f"Queuing for tenant: {tenant.name}")
            with tenant_context(tenant):
                add_task("gen_obligations")

        self.stdout.write(self.style.SUCCESS(f"Queued for {tenants.count()} tenant(s)"))
