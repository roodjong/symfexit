from decimal import Decimal

from django.test import TestCase
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.members.admin import Member
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Payment,
    PaymentProvider,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
    Transaction,
)


class DummyPayViewTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)

        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Dummy", type="dummy", default=True,
        )
        self.user = Member.objects.create_user(email="dummy@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-dummy-pay",
            name="Dummy Pay Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)
        order = product.order(for_user=self.user, billing_address=self.billing_address)
        order.paid_using = self.provider
        order.save()
        self.obligation = order.get_or_create_next_payment_obligation(timezone="UTC")

    def _post(self, status, amount):
        return self.client.post(
            f"/dummy/pay/{self.obligation.id}",
            {"payment_status": status, "amount_euros": amount},
        )

    def test_paid_with_default_amount(self):
        response = self._post("paid", "10.00")
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get(obligation=self.obligation)
        self.assertEqual(payment.transaction.amount_cents, 1000)

    def test_paid_partial_amount(self):
        self._post("paid", "4.00")
        payment = Payment.objects.get(obligation=self.obligation)
        self.assertEqual(payment.transaction.amount_cents, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.credit_account)

    def test_paid_overpayment_credits_user(self):
        self._post("paid", "15.00")
        payment = Payment.objects.get(obligation=self.obligation)
        self.assertEqual(payment.transaction.amount_cents, 1000)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.credit_account)
        credit_txs = Transaction.objects.filter(credit_account=self.user.credit_account)
        self.assertEqual(credit_txs.count(), 1)
        self.assertEqual(credit_txs.first().amount_cents, 500)

    def test_cancelled_records_no_payment(self):
        self._post("cancelled", "10.00")
        self.assertFalse(Payment.objects.filter(obligation=self.obligation).exists())


class FakePayFormTest(TestCase):
    def test_amount_required(self):
        from symfexit.payments.dummy.forms import FakePayForm  # noqa: PLC0415

        form = FakePayForm({"payment_status": "paid"})
        self.assertFalse(form.is_valid())
        self.assertIn("amount_euros", form.errors)

    def test_amount_must_be_positive(self):
        from symfexit.payments.dummy.forms import FakePayForm  # noqa: PLC0415

        form = FakePayForm({"payment_status": "paid", "amount_euros": "0"})
        self.assertFalse(form.is_valid())
        self.assertIn("amount_euros", form.errors)
