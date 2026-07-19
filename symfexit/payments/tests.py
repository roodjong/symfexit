from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase
from django_tenants.test.cases import FastTenantTestCase

from symfexit.members.admin import Member
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Payment,
    PaymentObligation,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
    Transaction,
)
from symfexit.payments.services import record_receipt
from symfexit.payments.tasks import gen_obligations


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


class TestObligationOutstanding(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.user = Member.objects.create_user(email="outstanding@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-outstanding",
            name="Outstanding Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)
        order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.obligation = order.get_or_create_next_payment_obligation(timezone="UTC")

    def _record_payment(self, amount_cents):

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=amount_cents
        )
        return Payment.objects.create(
            obligation=self.obligation,
            paid_at=datetime(2026, 1, 1, tzinfo=UTC),
            transaction=tx,
        )

    def test_no_payments_outstanding_is_full(self):
        self.assertEqual(self.obligation.outstanding_cents, 1000)
        self.assertFalse(self.obligation.is_fully_paid)

    def test_partial_payment(self):
        self._record_payment(400)
        self.assertEqual(self.obligation.outstanding_cents, 600)
        self.assertFalse(self.obligation.is_fully_paid)

    def test_fully_paid_via_multiple_payments(self):
        self._record_payment(400)
        self._record_payment(600)
        self.assertEqual(self.obligation.outstanding_cents, 0)
        self.assertTrue(self.obligation.is_fully_paid)

    def test_overpaid_is_negative_and_still_fully_paid(self):
        self._record_payment(1500)
        self.assertEqual(self.obligation.outstanding_cents, -500)
        self.assertTrue(self.obligation.is_fully_paid)


class TestMemberCreditBalance(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        self.user = Member.objects.create_user(email="creditbal@example.com")

    def test_no_credit_account_returns_zero(self):
        self.assertIsNone(self.user.credit_account)
        self.assertEqual(self.user.credit_balance_cents, 0)

    def test_credit_balance_reflects_account_movements(self):
        bank_account, _ = Account.get_bank_account()
        credit_account = self.user.get_or_create_credit_account()
        # Customer overpaid €5: bank debited, credit account credited (liability up)
        Transaction.objects.create(
            credit_account=credit_account, debit_account=bank_account, amount_cents=500
        )
        self.assertEqual(self.user.credit_balance_cents, 500)

        # Apply €3 of credit toward an invoice: credit account debited (liability down)
        ar_account, _ = Account.get_accounts_receivable_account()
        Transaction.objects.create(
            credit_account=ar_account, debit_account=credit_account, amount_cents=300
        )
        self.assertEqual(self.user.credit_balance_cents, 200)


class TestApplyMemberCredit(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.user = Member.objects.create_user(email="apply@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        self.product = Product.objects.create(
            enabled=True,
            sku="test-apply",
            name="Apply Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=1)
        self.order = self.product.order(for_user=self.user, billing_address=self.billing_address)

    def _credit_user(self, cents):
        bank_account, _ = Account.get_bank_account()
        credit_account = self.user.get_or_create_credit_account()
        Transaction.objects.create(
            credit_account=credit_account,
            debit_account=bank_account,
            amount_cents=cents,
        )

    def test_no_credit_no_payment_applied(self):
        obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        self.assertEqual(obligation.outstanding_cents, 1000)

        self.assertFalse(Payment.objects.filter(obligation=obligation).exists())

    def test_credit_partially_applied(self):
        self._credit_user(400)  # €4 credit; obligation €10
        obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        self.assertEqual(obligation.outstanding_cents, 600)
        self.assertEqual(self.user.credit_balance_cents, 0)

    def test_credit_fully_covers_obligation(self):
        self._credit_user(1500)  # €15 credit; obligation €10
        obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        self.assertEqual(obligation.outstanding_cents, 0)
        self.assertTrue(obligation.is_fully_paid)
        # €5 of credit remains for the next obligation
        self.assertEqual(self.user.credit_balance_cents, 500)

    def test_signup_user_gets_no_credit_application(self):
        """Order with no ordered_for: apply_member_credit is a no-op."""
        no_user_order = self.product.order(for_user=None, billing_address=self.billing_address)
        obligation = no_user_order.get_or_create_next_payment_obligation(timezone="UTC")
        self.assertEqual(obligation.outstanding_cents, 1000)


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


class TestGeneratePaymentObligations(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.user = Member.objects.create_user(email="testuser@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Roghorst 1",
            city="Nijmegen",
            postal_code="6525AG",
        )
        self.product = Product.objects.create(
            enabled=True,
            sku="lid",
            name="Lidmaatschap",
            price_euros=Decimal(10),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=3)

    def _create_order(self, cancelled=False):
        order = self.product.order(for_user=self.user, billing_address=self.billing_address)
        if cancelled:
            order.cancel()
        return order

    def test_creates_obligations_for_active_orders(self):
        order = self._create_order()

        gen_obligations()

        self.assertTrue(PaymentObligation.objects.filter(order=order).exists())

    def test_skips_cancelled_orders(self):
        order = self._create_order(cancelled=True)

        gen_obligations()

        self.assertFalse(PaymentObligation.objects.filter(order=order).exists())

    def test_idempotent(self):
        self._create_order()

        gen_obligations()
        count_after_first = PaymentObligation.objects.count()

        gen_obligations()
        count_after_second = PaymentObligation.objects.count()

        self.assertEqual(count_after_first, count_after_second)

    def test_now_override_advances_to_future_period(self):
        """Override 'now' to a future date — the next obligation lands in that period."""
        from datetime import date as date_cls  # noqa: PLC0415

        self._create_order()

        # First run with current time creates the current quarter's obligation.
        gen_obligations()
        first_obligation = PaymentObligation.objects.first()

        # Now run with an override well into the future to roll forward.
        future = date_cls(2099, 6, 15)
        gen_obligations(now=future)

        # A second obligation should exist for a later period.
        self.assertEqual(PaymentObligation.objects.count(), 2)
        new = PaymentObligation.objects.exclude(pk=first_obligation.pk).get()
        self.assertGreaterEqual(
            (new.year, new.period), (first_obligation.year, first_obligation.period)
        )

    def test_quarterly_billing_over_year_with_credit_carryforward(self):
        """Simulate a full year of quarterly billing with overpayment credit carrying forward."""
        order = self._create_order()
        order.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        order.save()

        # Q1: Generate first obligation and overpay by €5
        gen_obligations(now=datetime(2026, 1, 15, tzinfo=UTC))
        q1_obligation = PaymentObligation.objects.get(order=order, year=2026, period=0)
        self.assertEqual(q1_obligation.outstanding_cents, 1000)  # €10

        # Simulate overpayment: pay €15 for a €10 obligation
        # This will create a €10 payment and €5 credit for the user
        record_receipt(q1_obligation, amount_cents=1500)

        # Verify €5 credit was created for the user
        self.user.refresh_from_db()
        self.assertEqual(self.user.credit_balance_cents, 500)

        # Q2: Generate second obligation - credit should be auto-applied
        gen_obligations(now=datetime(2026, 4, 1, tzinfo=UTC))
        q2_obligation = PaymentObligation.objects.get(order=order, year=2026, period=3)
        # €10 obligation minus €5 credit = €5 outstanding
        self.assertEqual(q2_obligation.outstanding_cents, 500)
        # Credit should be consumed
        self.user.refresh_from_db()
        self.assertEqual(self.user.credit_balance_cents, 0)

        # Q3: Generate third obligation - no credit, full amount outstanding
        gen_obligations(now=datetime(2026, 7, 1, tzinfo=UTC))
        q3_obligation = PaymentObligation.objects.get(order=order, year=2026, period=6)
        self.assertEqual(q3_obligation.outstanding_cents, 1000)

        # Q4: Generate fourth obligation
        gen_obligations(now=datetime(2026, 10, 1, tzinfo=UTC))
        q4_obligation = PaymentObligation.objects.get(order=order, year=2026, period=9)
        self.assertEqual(q4_obligation.outstanding_cents, 1000)

        # Verify all 4 quarterly obligations were created with correct periods
        obligations = PaymentObligation.objects.filter(order=order).order_by("period")
        self.assertEqual(obligations.count(), 4)
        periods = list(obligations.values_list("period", flat=True))
        self.assertEqual(periods, [0, 3, 6, 9])  # Jan, Apr, Jul, Oct

    def test_quarterly_billing_with_price_increase(self):
        """Simulate quarterly billing where the subscription price increases mid-year."""
        order = self._create_order()
        order.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        order.save()

        # Q1: Generate first obligation at €10
        gen_obligations(now=datetime(2026, 1, 15, tzinfo=UTC))
        q1_obligation = PaymentObligation.objects.get(order=order, year=2026, period=0)
        self.assertEqual(q1_obligation.outstanding_cents, 1000)  # €10

        # Pay Q1 obligation
        record_receipt(q1_obligation, amount_cents=1000)

        # Q2: Generate second obligation at €10
        gen_obligations(now=datetime(2026, 4, 1, tzinfo=UTC))
        q2_obligation = PaymentObligation.objects.get(order=order, year=2026, period=3)
        self.assertEqual(q2_obligation.outstanding_cents, 1000)  # €10

        # Price increase: Update the order's price to €20 for future periods
        order.product_price_euros = Decimal("20.00")
        order.save()

        # Q3: Generate third obligation - should now be €20
        gen_obligations(now=datetime(2026, 7, 1, tzinfo=UTC))
        q3_obligation = PaymentObligation.objects.get(order=order, year=2026, period=6)
        self.assertEqual(q3_obligation.outstanding_cents, 2000)  # €20

        # Q4: Generate fourth obligation - should remain €20
        gen_obligations(now=datetime(2026, 10, 1, tzinfo=UTC))
        q4_obligation = PaymentObligation.objects.get(order=order, year=2026, period=9)
        self.assertEqual(q4_obligation.outstanding_cents, 2000)  # €20

        # Verify all 4 obligations exist with correct prices
        obligations = PaymentObligation.objects.filter(order=order).order_by("period")
        self.assertEqual(obligations.count(), 4)
        amounts = list(obligations.values_list("transaction__amount_cents", flat=True))
        self.assertEqual(amounts, [1000, 1000, 2000, 2000])  # €10, €10, €20, €20
