from django.conf import settings
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from hashids import Hashids

hashids = Hashids(min_length=8, salt=settings.SECRET_KEY)

# Create your models here.
class Payable(models.Model):
    class Status(models.TextChoices):
        INITIAL = "created", _("Created")
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")
    id = models.AutoField(primary_key=True)
    price = models.IntegerField() # in cents
    description = models.TextField()
    payment_status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIAL)
    created_at = models.DateTimeField(auto_now_add=True)

    return_url = models.URLField(null=True)

    def __str__(self):
        return "{} voor {:.02f} ({})".format(self.description, self.price / 100, Payable.Status(self.payment_status).label)

    @property
    def eid(self):
        return hashids.encode(self.id)

    @classmethod
    def get_or_404(cls, eid) -> "Payable":
        id = hashids.decode(eid)[0]
        return get_object_or_404(cls, id=id)
