from datetime import date
from decimal import Decimal

from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.payments.models import (
    Account,
    Order,
    Payment,
    PaymentProvider,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
    Transaction,
)
from symfexit.signup.models import MembershipApplication


class ReturnViewTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)

        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Dummy",
            type="dummy",
            default=True,
        )
        self.product = Product.objects.create(
            enabled=True,
            sku="signup-product",
            name="Signup Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=1)

        self.application = MembershipApplication.objects.create(
            first_name="Test",
            last_name="User",
            email="signup@example.com",
            phone_number="+31600000000",
            birth_date=date(2000, 1, 1),
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
            payment_amount_euros=Decimal("10.00"),
        )

    def _create_order(self):
        from symfexit.payments.models import BillingAddress  # noqa: PLC0415

        billing = BillingAddress.objects.create(
            user=None,
            name=f"{self.application.first_name} {self.application.last_name}",
            email=self.application.email,
            address=self.application.address,
            city=self.application.city,
            postal_code=self.application.postal_code,
        )
        order, obligation = Order.objects.create_with_obligation(
            product=self.product,
            billing_address=billing,
            price_euros=Decimal("10.00"),
            paid_using=self.provider,
        )
        self.application._order = order
        self.application.save()
        return order, obligation

    def _record_payment(self, obligation, amount_cents):
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        from django.utils import timezone  # noqa: PLC0415

        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=amount_cents
        )
        Payment.objects.create(
            order=obligation.order,
            obligation=obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

    def _get(self):
        return self.client.get(f"/aanmelden/return/{self.application.eid}")

    def test_no_order_returns_404(self):
        response = self._get()
        self.assertEqual(response.status_code, 404)

    def test_cancelled_order_renders_cancelled(self):
        from django.utils import timezone  # noqa: PLC0415

        order, _ = self._create_order()
        order.cancelled_at = timezone.now()
        order.save()

        response = self._get()
        self.assertTemplateUsed(response, "signup/cancelled.html")

    def test_no_payments_renders_open(self):
        self._create_order()
        response = self._get()
        self.assertTemplateUsed(response, "signup/open.html")

    def test_partial_payment_renders_open(self):
        _, obligation = self._create_order()
        self._record_payment(obligation, 400)  # €4 of €10
        response = self._get()
        self.assertTemplateUsed(response, "signup/open.html")

    def test_fully_paid_renders_return(self):
        _, obligation = self._create_order()
        self._record_payment(obligation, 1000)
        response = self._get()
        self.assertTemplateUsed(response, "signup/return.html")

    def test_overpayment_still_renders_return(self):
        _, obligation = self._create_order()
        self._record_payment(obligation, 1500)
        response = self._get()
        self.assertTemplateUsed(response, "signup/return.html")


class CreateUserSignupOverpaymentTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Dummy",
            type="dummy",
            default=True,
        )
        self.product = Product.objects.create(
            enabled=True,
            sku="signup-overpay",
            name="Signup Overpay Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=1)

        from symfexit.membership.models import MembershipType  # noqa: PLC0415

        self.mtype = MembershipType.objects.create(
            name="Standard", enabled=True, custom_amount_product=self.product
        )

        self.application = MembershipApplication.objects.create(
            first_name="Over",
            last_name="Payer",
            email="over@example.com",
            phone_number="+31600000000",
            birth_date=date(2000, 1, 1),
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
            payment_amount_euros=Decimal("10.00"),
            membership_type=self.mtype,
        )

    def _record_payment(self, obligation, amount_cents):
        from django.utils import timezone  # noqa: PLC0415

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=amount_cents
        )
        Payment.objects.create(
            order=obligation.order,
            obligation=obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

    def test_overpayment_moves_to_user_credit_after_link(self):
        order, obligation = self.application.get_or_create_order(self.provider)
        # Customer paid €15 against a €10 obligation during signup.
        self._record_payment(obligation, 1500)
        self.assertEqual(obligation.outstanding_cents, -500)

        user = self.application.create_user()

        self.assertEqual(user.credit_balance_cents, 500)
        # Obligation is fully paid (over-paid), so future credit application is a no-op
        # (it would no-op anyway because outstanding is negative).
        obligation.refresh_from_db()
        self.assertTrue(obligation.is_fully_paid)

    def test_exact_payment_no_credit_movement(self):
        order, obligation = self.application.get_or_create_order(self.provider)
        self._record_payment(obligation, 1000)

        user = self.application.create_user()

        self.assertEqual(user.credit_balance_cents, 0)
        # No credit account was lazily created since there was nothing to credit.
        self.assertIsNone(user.credit_account)

    def test_no_payment_no_credit_movement(self):
        order, obligation = self.application.get_or_create_order(self.provider)
        # No Payments at all yet (e.g. user closed the tab during signup).

        user = self.application.create_user()

        self.assertEqual(user.credit_balance_cents, 0)
        self.assertIsNone(user.credit_account)
