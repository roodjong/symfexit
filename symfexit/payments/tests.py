from datetime import UTC, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from symfexit.members.admin import Member
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Order,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
    Transaction,
)


class TestBalance(TestCase):
    def test_credit_normal_balance_adds_correctly(self):
        revenue_account, _ = Account.get_revenue_account()
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account = Account.objects.create(
            name="Bank", description="Balance at the bank", code=1, credit_balance=False
        )
        # Someone just ordered a membership of 7 euros, this means we have an income of 700 but we
        # haven't received the money yet so we add 7 euros to the Accounts Receivable (debiteuren) account
        Transaction.objects.create(
            credit_account=revenue_account,
            debit_account=ar_account,
            amount_cents=700,
            part_of=uuid4(),
        )

        self.assertEqual(revenue_account.balance_cents(), 700)
        self.assertEqual(ar_account.balance_cents(), 700)

        # Our debitor just paid for the membership, which means the money is now in our bank and can
        # be resolved from the Accounts Receivable account
        Transaction.objects.create(
            credit_account=ar_account,
            debit_account=bank_account,
            amount_cents=700,
            part_of=uuid4(),
        )

        self.assertEqual(revenue_account.balance_cents(), 700)
        self.assertEqual(ar_account.balance_cents(), 0)
        self.assertEqual(bank_account.balance_cents(), 700)

    def test_negative_balance(self):
        bank_account = Account.objects.create(
            name="Bank", description="Balance at the bank", code=1, credit_balance=False
        )
        expenses_account = Account.objects.create(
            name="Expenses", description="Expenses", code=2, credit_balance=False
        )
        Transaction.objects.create(
            credit_account=bank_account,
            debit_account=expenses_account,
            amount_cents=700,
            part_of=uuid4(),
        )
        self.assertEqual(bank_account.balance_cents(), -700)
        self.assertEqual(expenses_account.balance_cents(), 700)


class TestNextPeriod(TestCase):
    def test_next_period_quarter(self):
        product = Product.objects.create(
            enabled=True,
            sku="lid",
            name="Lidmaatschap",
            price_euros=Decimal(10),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=3)
        user = Member.objects.create_user(email="testuser@example.com")
        billing_address = BillingAddress.objects.create(
            user=user,
            name="Test User",
            address="Roghorst 1",
            city="Nijmegen",
            postal_code="6525AG",
        )
        order = product.order(for_user=user, billing_address=billing_address)
        order.created_at = datetime(2025, 10, 18, 13, 10, 0, tzinfo=UTC)
        order.save()
        payment_obligation = order.get_or_create_next_payment_obligation(timezone="UTC")
        # The first time no payment obligations exist yet and the first payment happens on the day the order is made
        self.assertEqual(payment_obligation.year, 2025)
        self.assertEqual(payment_obligation.period, 9)

        # If the cron runs again on that day, no new obligation needs to be made yet
        next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2025, 10, 18, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_payment_obligation.year, 2025)
        self.assertEqual(next_payment_obligation.period, 9)

        # Later on the next payment obligation can be updated
        next_next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2025, 12, 18, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_next_payment_obligation.year, 2026)
        self.assertEqual(next_next_payment_obligation.period, 0)

    def test_next_period_half_year(self):
        product = Product.objects.create(
            enabled=True,
            sku="lid",
            name="Lidmaatschap",
            price_euros=Decimal(10),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=6)
        user = Member.objects.create_user(email="testuser@example.com")
        billing_address = BillingAddress.objects.create(
            user=user,
            name="Test User",
            address="Roghorst 1",
            city="Nijmegen",
            postal_code="6525AG",
        )
        order = product.order(for_user=user, billing_address=billing_address)
        order.created_at = datetime(2025, 1, 1, 13, 10, 0, tzinfo=UTC)
        order.save()
        payment_obligation = order.get_or_create_next_payment_obligation(timezone="UTC")
        # The first time no payment obligations exist yet and the first payment happens on the day the order is made
        self.assertEqual(payment_obligation.year, 2025)
        self.assertEqual(payment_obligation.period, 0)

        next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2025, 12, 18, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_payment_obligation.year, 2025)
        self.assertEqual(next_payment_obligation.period, 6)

        next_next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2026, 3, 18, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_next_payment_obligation.year, 2026)
        self.assertEqual(next_next_payment_obligation.period, 0)

    def test_next_period_day(self):
        product = Product.objects.create(
            enabled=True,
            sku="lid",
            name="Lidmaatschap",
            price_euros=Decimal(10),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.DAY, period=10)
        user = Member.objects.create_user(email="testuser@example.com")
        billing_address = BillingAddress.objects.create(
            user=user,
            name="Test User",
            address="Roghorst 1",
            city="Nijmegen",
            postal_code="6525AG",
        )
        order = product.order(for_user=user, billing_address=billing_address)
        order.created_at = datetime(2025, 12, 28, 13, 10, 0, tzinfo=UTC)
        order.save()
        payment_obligation = order.get_or_create_next_payment_obligation(timezone="UTC")
        # The first time no payment obligations exist yet and the first payment happens on the day the order is made
        self.assertEqual(payment_obligation.year, 2025)
        self.assertEqual(payment_obligation.period, 361)  # 28th of December

        next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2026, 1, 5, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_payment_obligation.year, 2026)
        self.assertEqual(next_payment_obligation.period, 6)  # 5th of January

        next_next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC", now=datetime(2026, 1, 15, 13, 10, 0, tzinfo=UTC)
        )
        self.assertEqual(next_next_payment_obligation.year, 2026)
        self.assertEqual(next_next_payment_obligation.period, 16)  # 15th

    def test_next_period_week(self):
        product = Product.objects.create(
            enabled=True,
            sku="lid",
            name="Lidmaatschap",
            price_euros=Decimal(10),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.WEEK, period=2)
        user = Member.objects.create_user(email="testuser@example.com")
        billing_address = BillingAddress.objects.create(
            user=user,
            name="Test User",
            address="Roghorst 1",
            city="Nijmegen",
            postal_code="6525AG",
        )
        order = product.order(for_user=user, billing_address=billing_address)
        order.created_at = datetime(2025, 12, 29, 13, 10, 0, tzinfo=UTC)  # Week 1 of 2026
        order.save()
        payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC",
        )
        # The first time no payment obligations exist yet and the first payment happens on the day the order is made
        self.assertEqual(payment_obligation.year, 2026)
        self.assertEqual(payment_obligation.period, 0)  # Week 1

        next_payment_obligation = order.get_or_create_next_payment_obligation(
            timezone="UTC",
            now=datetime(2026, 1, 15, 13, 10, 0, tzinfo=UTC),  # Week 2
        )
        self.assertEqual(next_payment_obligation.year, 2026)
        self.assertEqual(next_payment_obligation.period, 2)  # Week 3
