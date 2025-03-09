from django.db import models
from django_tenants.models import DomainMixin, TenantMixin
from django_tenants.utils import tenant_context


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        with tenant_context(self):
            # Set the constance SITE_TITLE if not set yet
            from constance import config

            if config._backend.get("SITE_TITLE") is None:
                config.SITE_TITLE = self.name


class Domain(DomainMixin):
    pass
