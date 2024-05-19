from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from hashids import Hashids

hashids = Hashids(min_length=8, salt=settings.SECRET_KEY)

User = get_user_model()


class BillingAddress(models.Model):
    class Meta:
        verbose_name = _("billing address")
        verbose_name_plural = _("billing addresses")

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "[{}] {}: {}\n{}\n{}".format(
            self.id, self.name, self.address, self.postal_code, self.city
        )


class Order(models.Model):
    class Status(models.TextChoices):
        INITIAL = "created", _("Created")
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    id = models.AutoField(primary_key=True)
    price = models.IntegerField()  # in cents
    description = models.TextField()
    address = models.ForeignKey("BillingAddress", on_delete=models.PROTECT)
    payment_status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.INITIAL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True)
    payment_method = models.CharField(max_length=100, null=True)

    return_url = models.URLField(null=True)

    subscription = models.ForeignKey(
        "Subscription", on_delete=models.RESTRICT, null=True
    )

    def __str__(self):
        return "{} voor {:.02f} ({})".format(
            self.description, self.price / 100, Order.Status(self.payment_status).label
        )

    @property
    def eid(self):
        return hashids.encode(self.id)

    @classmethod
    def get_or_404(cls, eid) -> "Order":
        id = hashids.decode(eid)[0]
        return get_object_or_404(cls, id=id)

    def save(self, *args, **kwargs):
        if self.payment_status == Order.Status.PAID and self.done_at is None:
            self.done_at = timezone.now()
        return super().save(*args, **kwargs)


class SubscriptionManager(models.Manager):
    def current(self):
        return self.get_queryset().filter(active_from_to__contains=timezone.now())


class Subscription(models.Model):
    class PeriodUnit(models.TextChoices):
        DAY = "day", _("Day")
        WEEK = "week", _("Week")
        MONTH = "month", _("Month")
        YEAR = "year", _("Year")

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    address = models.ForeignKey("BillingAddress", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    active_from_to = DateTimeRangeField(null=False)
    price_per_period = models.IntegerField()  # in cents
    period_quantity = models.IntegerField()
    period_unit = models.CharField(max_length=5, choices=PeriodUnit.choices)

    objects = SubscriptionManager()

    @property
    def eid(self):
        return hashids.encode(self.id)

    @property
    def is_current(self):
        return self.active_from_to.lower <= timezone.now() < self.active_from_to.upper

    def new_order(self, *, initial, return_url, description=None):
        if description is None:
            description = "Subscription for {}".format(self.address.name)
            if initial == False:
                description += " (initial payment)"
        return Order.objects.create(
            price=self.price_per_period,
            description=description,
            address=self.address,
            subscription=self,
            return_url=return_url,
        )

    @classmethod
    def get_or_404(cls, eid) -> "Subscription":
        id = hashids.decode(eid)[0]
        return get_object_or_404(cls, id=id)

    def __str__(self):
        return "Subscription for {}".format(self.address.name)
