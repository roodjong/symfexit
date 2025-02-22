from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from hashids import Hashids

hashids = Hashids(min_length=8, salt=settings.SECRET_KEY)

User = get_user_model()


class PeriodUnit(models.TextChoices):
    DAY = "day", _("Day")
    WEEK = "week", _("Week")
    MONTH = "month", _("Month")
    YEAR = "year", _("Year")


class BillingAddress(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("user"))
    name = models.CharField(_("name"), max_length=100)
    address = models.CharField(_("address"), max_length=100)
    city = models.CharField(_("city"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("billing address")
        verbose_name_plural = _("billing addresses")

    def __str__(self):
        return f"[{self.id}] {self.name}: {self.address}\n{self.postal_code}\n{self.city}"


class Payment(models.Model):
    class Status(models.TextChoices):
        INITIAL = "created", _("Created")
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    id = models.AutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.INITIAL,
        verbose_name=_("payment status"),
    )

    order = models.ForeignKey(
        "Order",
        on_delete=models.RESTRICT,
        null=False,
        verbose_name=_("order"),
    )

    def __str__(self):
        return _("Payment for {order}").format(order=self.order)


class Order(models.Model):
    """An order is a subscription instance.

    When a subscription is started, we say the user "ordered" the subscription product.

    The order will receive multiple payments, which fulfill the subscription payment structure.
    """

    id = models.AutoField(primary_key=True)

    description = models.TextField(_("description"))
    address = models.ForeignKey(
        "BillingAddress", on_delete=models.PROTECT, verbose_name=_("billing address")
    )

    subscription = models.ForeignKey(
        "Subscription",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("subscription"),
    )
    price_per_period = models.IntegerField()  # in cents
    period_quantity = models.IntegerField()
    period_unit = models.CharField(max_length=5, choices=PeriodUnit.choices)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")

    def __str__(self):
        return _("{description} for {price:.02f}").format(
            description=self.description, price=self.price / 100
        )

    @property
    def eid(self):
        return hashids.encode(self.id)

    eid.fget.short_description = _("external identifier")

    @classmethod
    def get_or_404(cls, eid) -> "Order":
        id = hashids.decode(eid)[0]
        return get_object_or_404(cls, id=id)


class Subscription(models.Model):
    """A subscription is a type of product that requires multiple payments.

    The payment structure of a subscription is given by the price_per_period,
    the period_quantity and the period_unit.

    Subscriptions have an indefinite duration by default.
    """

    id = models.AutoField(primary_key=True)
    name = models.TextField(null=False, blank=False)
    description = models.TextField(null=False, blank=True)

    price_per_period = models.IntegerField(
        null=True, blank=True
    )  # in cents, if null then it must be set in the order
    period_quantity = models.IntegerField()
    period_unit = models.CharField(max_length=5, choices=PeriodUnit.choices)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return self.description

    @property
    def eid(self):
        return hashids.encode(self.id)

    eid.fget.short_description = _("external identifier")

    @classmethod
    def get_or_404(cls, eid) -> "Subscription":
        id = hashids.decode(eid)[0]
        return get_object_or_404(cls, id=id)

    def new_order(self, *, initial, return_url, description=None):
        """Create a subscription "instance" of this subscription type."""
        if description is None:
            description = f"Subscription for {self.address.name}"
        return Order.objects.create(
            price=self.price_per_period,
            description=description,
            address=self.address,
            subscription=self,
            return_url=return_url,
        )
