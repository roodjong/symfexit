import calendar
import os
import time
import uuid
import zoneinfo
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _
from hashids import Hashids

from symfexit.members.admin import Member

hashids = Hashids(min_length=8, salt=settings.SECRET_KEY)

User = get_user_model()

ACCOUNT_ACCOUNTS_RECEIVABLE = 13011
ACCOUNT_REVENUE = 82811


def tigerbeetle_id():
    """A type of universal unique identifier utilising timestamps and randomness.

    Similar to UUIDv7 but using recommendations from tigerbeetle
    """
    value = bytearray(6)
    timestamp = int(time.time() * 1000)
    value[0] = (timestamp >> 40) & 0xFF
    value[1] = (timestamp >> 32) & 0xFF
    value[2] = (timestamp >> 24) & 0xFF
    value[3] = (timestamp >> 16) & 0xFF
    value[4] = (timestamp >> 8) & 0xFF
    value[5] = timestamp & 0xFF
    # Fake UUID as it does not set the version/variant fields
    return uuid.UUID(bytes=bytes(value + os.urandom(10)))


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

    @classmethod
    def get_or_create_for_user(cls, user: Member):
        address = (
            user.billingaddress_set.filter(
                address=user.address, city=user.city, postal_code=user.postal_code
            )
            .order_by("-created_at")
            .first()
        )
        if not address:
            if not (user.address and user.city and user.postal_code):
                return None
            address = cls.objects.create(
                user_id=user.id,
                name=user.get_full_name(),
                address=user.address,
                city=user.city,
                postal_code=user.postal_code,
            )
        return address


class Transaction(models.Model):
    id = models.UUIDField(primary_key=True, default=tigerbeetle_id, editable=False)
    credit_account = models.ForeignKey(
        "payments.account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="credit_transactions",
    )
    debit_account = models.ForeignKey(
        "payments.account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="debit_transactions",
    )
    amount_cents = models.IntegerField()
    # A journal entry can consist of many transactions. They are grouped using the "part_of" UUID (which is arbitrary)
    part_of = models.UUIDField(default=tigerbeetle_id)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        credit_account = self.get_credit_account() or self.credit_account_id
        debit_account = self.get_debit_account() or self.debit_account_id
        return f"Transaction of €{self.amount_cents / 100:.2f} from {credit_account} to {debit_account}"

    def get_credit_account(self) -> Optional["Account"]:
        return Account.objects.filter(id=self.credit_account_id).first()

    def get_debit_account(self) -> Optional["Account"]:
        return Account.objects.filter(id=self.debit_account_id).first()


class GeneralLedger(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    credit_balance = models.BooleanField(
        help_text=_(
            "Assets and expenses are increased with debits, decreased with credits. Liabilities, equity, and income are increased with credits, decreased with debits. Tick this if the account increases with credits. This makes sure the balance is shown correctly."
        )
    )

    class Meta:
        verbose_name = _("general ledger")

    def __str__(self):
        return self.name

    def balance_cents(self):
        credit_balances = Transaction.objects.filter(credit_account__general_ledger=self).aggregate(
            models.Sum("amount_cents", default=0)
        )["amount_cents__sum"]
        debit_balances = Transaction.objects.filter(debit_account__general_ledger=self).aggregate(
            models.Sum("amount_cents", default=0)
        )["amount_cents__sum"]
        if self.credit_balance:
            return credit_balances - debit_balances
        else:
            return debit_balances - credit_balances


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.PositiveIntegerField(unique=True)
    name = models.CharField()
    description = models.TextField()
    general_ledger = models.ForeignKey(GeneralLedger, on_delete=models.SET_NULL, null=True)
    credit_balance = models.BooleanField(
        help_text=_(
            "Assets and expenses are increased with debits, decreased with credits. Liabilities, equity, and income are increased with credits, decreased with debits. Tick this if the account increases with credits. This makes sure the balance is shown correctly."
        )
    )

    def __str__(self):
        return f"{self.name} ({self.code})"

    @classmethod
    def get_accounts_receivable_account(cls):
        """Money that has been invoiced, but not received yet.

        In RGS this is mapped to BVorDebHad (13011).
        See: https://www.boekhoudplaza.nl/rgs_rekeningen/BVorDebHad&KB=R&kzB=SVC/Debiteuren.htm
        """
        return cls.objects.get_or_create(
            code=ACCOUNT_ACCOUNTS_RECEIVABLE,
            defaults={
                "name": _("Accounts Receivable"),
                "description": _(
                    "Accounts receivable represents money owed by entities to the firm on the sale of products or services on credit. In RGS this is mapped to BVorDebHad (13011). See: https://www.boekhoudplaza.nl/rgs_rekeningen/BVorDebHad&KB=R&kzB=SVC/Debiteuren.htm"
                ),
                "credit_balance": False,
            },
        )

    @classmethod
    def get_revenue_account(cls):
        """Balance account where association revenue is collected.

        In RGS this is mapped to WLbeLbvLbv (82811).
        See: https://www.boekhoudplaza.nl/rgs_rekeningen/WLbeLbvLbv&KB=R&kzB=SVC&rgsv=WLbeLbvLbv/Ledenbetalingen_inclusief_reeds_betaalde_voorschotten.htm
        """
        return cls.objects.get_or_create(
            code=ACCOUNT_REVENUE,
            defaults={
                "name": _("Revenue"),
                "description": _(
                    "Membership revenue balance account. In RGS this is mapped to WLbeLbvLbv (82811). See: https://www.boekhoudplaza.nl/rgs_rekeningen/WLbeLbvLbv&KB=R&kzB=SVC&rgsv=WLbeLbvLbv/Ledenbetalingen_inclusief_reeds_betaalde_voorschotten.htm"
                ),
                "credit_balance": True,
            },
        )

    def credit_balance_cents(self):
        return self.credit_transactions.aggregate(models.Sum("amount_cents", default=0))[
            "amount_cents__sum"
        ]

    def debit_balance_cents(self):
        return self.debit_transactions.aggregate(models.Sum("amount_cents", default=0))[
            "amount_cents__sum"
        ]

    def balance_cents(self):
        credit_balance = self.credit_transactions.aggregate(models.Sum("amount_cents", default=0))[
            "amount_cents__sum"
        ]
        debit_balance = self.debit_transactions.aggregate(models.Sum("amount_cents", default=0))[
            "amount_cents__sum"
        ]
        if self.credit_balance:
            return credit_balance - debit_balance
        else:
            return debit_balance - credit_balance


class ProductType(models.TextChoices):
    SUBSCRIPTION = "subscription", _("Subscription")


class Product(models.Model):
    enabled = models.BooleanField(_("enabled"))
    sku = models.SlugField(_("product sku"), max_length=100)
    name = models.CharField(_("product name"), max_length=100)
    price_euros = models.DecimalField(max_digits=8, decimal_places=2)
    type = models.CharField(choices=ProductType, default=ProductType.SUBSCRIPTION)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    def __str__(self):
        return f"{self.name} (€{self.price_euros})"

    def price_cents(self):
        return int(self.price_euros * 100)

    def order(self, for_user: Member, billing_address: BillingAddress):
        return Order.objects.create(
            product=self,
            product_sku=self.sku,
            product_name=self.name,
            product_price_euros=self.price_euros,
            subscription=self.subscription,
            subscription_period_unit=self.subscription.period_unit,
            subscription_period=self.subscription.period,
            ordered_for=for_user,
            ordered_for_billing_address=billing_address,
        )


class Subscription(models.Model):
    """If the product.type is SUBSCRIPTION, this contains the information about the subscription"""

    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    period_unit = models.CharField(choices=PeriodUnit)
    period = models.IntegerField(
        help_text=_("How many of the period unit before the subscription repeats.")
    )

    def __str__(self):
        return f"Subscription for {self.product.name}"


def _weeks_for_year(year):
    last_week = date(year, 12, 28)
    return last_week.isocalendar().week


class Order(models.Model):
    # For now only one order item per order is possible
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_sku = models.CharField(_("product sku"), max_length=100)
    product_name = models.CharField(_("product name"), max_length=100)
    product_price_euros = models.DecimalField(max_digits=8, decimal_places=2)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True)
    subscription_period_unit = models.CharField(choices=PeriodUnit, blank=True)
    subscription_period = models.IntegerField(
        help_text=_("How many of the period unit before the subscription repeats."), null=True
    )

    ordered_for = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    ordered_for_billing_address = models.ForeignKey(BillingAddress, on_delete=models.PROTECT)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order for product {self.product_name} for user {self.ordered_for.get_full_name()}"

    def product_price_cents(self):
        return int(self.product_price_euros * 100)

    def _get_current_period(self, now: datetime):
        match self.subscription_period_unit:
            case PeriodUnit.DAY:
                return now.year, now.timetuple().tm_yday - 1
            case PeriodUnit.WEEK:
                return now.isocalendar().year, now.isocalendar().week - 1
            case PeriodUnit.MONTH:
                return now.year, now.month - 1
            case PeriodUnit.YEAR:
                return now.year, now.year

    def _get_period_limit(self, year: int):
        match self.subscription_period_unit:
            case PeriodUnit.DAY:
                return 365 + int(calendar.isleap(year))
            case PeriodUnit.WEEK:
                return _weeks_for_year(year)
            case PeriodUnit.MONTH:
                return 12
            case PeriodUnit.YEAR:
                return float("inf")  # Years don't wrap

    def _get_period_initial(self):
        match self.subscription_period_unit:
            case PeriodUnit.DAY:
                return (self.created_at.timetuple().tm_yday - 1, self.created_at.year)
            case PeriodUnit.WEEK:
                return (self.created_at.isocalendar().week - 1, self.created_at.isocalendar().year)
            case PeriodUnit.MONTH:
                return (self.created_at.month - 1, self.created_at.year)
            case PeriodUnit.YEAR:
                return (self.created_at.year, self.created_at.year)

    def _period_to_datetime(self, year: int, period: int, *, timezone: zoneinfo.ZoneInfo):
        match self.subscription_period_unit:
            case PeriodUnit.DAY:
                return datetime(year, 1, 1, tzinfo=timezone) + timedelta(days=period)
            case PeriodUnit.WEEK:
                return datetime.strptime(f"{year}-W{period + 1}-1", "%Y-W%W-%w").replace(
                    tzinfo=timezone
                )
            case PeriodUnit.MONTH:
                return datetime(year, period + 1, 1, tzinfo=timezone)
            case PeriodUnit.YEAR:
                return datetime(year, 1, 1, tzinfo=timezone)

    def _calculate_next_period(self, previous_year: int, previous_period: int):
        if self.subscription_period_unit == PeriodUnit.YEAR:
            # Special case: years don't wrap within a year
            next_period = previous_year + self.subscription_period
            next_year = previous_year + self.subscription_period
        else:
            limit = self._get_period_limit(previous_year)
            next_period = (previous_period + self.subscription_period) % limit
            year_rollover = (previous_period + self.subscription_period) >= limit
            next_year = previous_year + int(year_rollover)
        return next_year, next_period

    def get_or_create_next_payment_obligation(self, *, timezone, now: datetime = None):
        timezone = zoneinfo.ZoneInfo(timezone)
        if now is None:
            now = datetime.now(tz=timezone)
        previous_obligation = self.paymentobligation_set.order_by("-year", "-period").first()
        # Define period extractors and limits for each unit

        if previous_obligation is None:
            next_period, next_year = self._get_period_initial()
        else:
            previous_period = previous_obligation.period
            previous_year = previous_obligation.year
            current_period = self._get_current_period(now)

            if (previous_year, previous_period) >= current_period:
                next_period = previous_period
                next_year = previous_year
            else:
                next_year, next_period = self._calculate_next_period(previous_year, previous_period)

        # Convert the year and period to a pay_before datetime
        pay_before = self._period_to_datetime(
            *self._calculate_next_period(next_year, next_period),
            timezone=timezone,
        ) - timedelta(seconds=1)

        obligation, _ = PaymentObligation.objects.get_or_create(
            order=self,
            year=next_year,
            period=next_period,
            pay_before=pay_before,
            defaults={"ordered_for_billing_address": self.ordered_for_billing_address},
        )
        return obligation


class PaymentObligation(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    year = models.IntegerField(null=True, blank=True)
    period = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    pay_before = models.DateTimeField()
    amount_euros = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    ordered_for_billing_address = models.ForeignKey(
        BillingAddress, on_delete=models.PROTECT, null=False, blank=False
    )

    def __str__(self):
        return f"Payment obligation for order {self.order.id} for year {self.year} period {self.period}"

    def save(self, *args, **kwargs):
        if self.amount_euros is None:
            self.amount_euros = self.order.product_price_euros
        if self.pay_before is None:
            self.pay_before = self.order._period_to_datetime(
                *self.order._calculate_next_period(self.year, self.period)
            ) - timedelta(seconds=1)
        super().save(*args, **kwargs)


class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    obligation = models.ForeignKey(PaymentObligation, on_delete=models.SET_NULL, null=True)
    # When this payment was made according to the payer
    paid_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for order {self.order.id} made at {self.paid_at}"
