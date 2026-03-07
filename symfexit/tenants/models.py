from django.db import models
from django_tenants.models import DomainMixin, TenantMixin
from django_tenants.utils import tenant_context


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    site_title = models.CharField(max_length=100, blank=True, null=True, default="Membersite")  # noqa: DJ001
    logo_image = models.CharField(max_length=255, blank=True, default="")
    main_site = models.URLField(blank=True, default="https://roodjongeren.nl/")
    homepage_current = models.IntegerField(blank=True, null=True, default=0)
    payment_tiers_json = models.JSONField(blank=True, null=True, default=list)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    pass
