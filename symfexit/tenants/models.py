from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Client(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    config = models.JSONField(default=dict, blank=True)

    # default true, schema will be automatically created and synced when it is saved
    auto_create_schema = True

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if self.config is None:
            self.config = {}
        super().save(*args, **kwargs)
        if is_new and "SITE_TITLE" not in self.config:
            self.config["SITE_TITLE"] = self.name
            self.save(update_fields=["config"])


class Domain(DomainMixin):
    pass
