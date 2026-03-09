from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase

from symfexit.members.admin import Member
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Order,
    Payment,
    PaymentObligation,
    PaymentProvider,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
)
from symfexit.payments.mollie.models import MollieCustomer, MolliePayment, MollieSettings
from symfexit.payments.mollie.views import mollie_webhook


class MollieWebhookTest(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Mollie Test",
            type="mollie",
            default=True,
        )
        self.mollie_settings = MollieSettings.objects.create(
            payment_provider=self.provider,
            test_api_key="test_xxx",
        )

        self.user = Member.objects.create_user(email="mollie@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-mollie",
            name="Test Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        order = product.order(for_user=self.user, billing_address=self.billing_address)
        order.paid_using = self.provider
        order.save()

        self.obligation = order.get_or_create_next_payment_obligation(timezone="UTC")

        self.mollie_payment = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_test123",
        )

        self.factory = RequestFactory()

    def _make_mock_mollie_data(self, status, is_paid):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: status if k == "status" else None
        mock.is_paid.return_value = is_paid
        return mock

    def _post_webhook(self, payment_id):
        request = self.factory.post("/mollie/webhook/", {"id": payment_id})
        return mollie_webhook(request)

    def test_paid_creates_payment_and_transaction(self):
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data("paid", True)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            response = self._post_webhook("tr_test123")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Payment.objects.filter(obligation=self.obligation).exists())

        payment = Payment.objects.get(obligation=self.obligation)
        self.assertEqual(payment.order, self.obligation.order)
        self.assertEqual(payment.paid_using, self.provider)
        self.assertEqual(payment.transaction.amount_cents, 1000)

        self.mollie_payment.refresh_from_db()
        self.assertEqual(self.mollie_payment.status, "paid")

    def test_paid_is_idempotent(self):
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data("paid", True)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")
            self._post_webhook("tr_test123")

        self.assertEqual(Payment.objects.filter(obligation=self.obligation).count(), 1)

    def test_failed_does_not_create_payment(self):
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data("failed", False)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            response = self._post_webhook("tr_test123")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.filter(obligation=self.obligation).exists())

        self.mollie_payment.refresh_from_db()
        self.assertEqual(self.mollie_payment.status, "failed")

    def test_unknown_payment_id_returns_200(self):
        response = self._post_webhook("tr_unknown")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.filter(obligation=self.obligation).exists())

    def test_missing_id_returns_200(self):
        request = self.factory.post("/mollie/webhook/", {})
        response = mollie_webhook(request)
        self.assertEqual(response.status_code, 200)

    def test_get_not_allowed(self):
        request = self.factory.get("/mollie/webhook/")
        response = mollie_webhook(request)
        self.assertEqual(response.status_code, 405)


def _make_mock_mandates(mandates):
    return {"_embedded": {"mandates": mandates}}


class MollieStartPaymentFlowTest(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Mollie Test",
            type="mollie",
            default=True,
        )
        self.mollie_settings = MollieSettings.objects.create(
            payment_provider=self.provider,
            test_api_key="test_xxx",
        )

        self.user = Member.objects.create_user(email="flow@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-flow",
            name="Flow Product",
            price_euros=Decimal("15.50"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()

        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        self.factory = RequestFactory()

    def _make_request(self):
        request = self.factory.get("/pay/")
        request.META["SERVER_NAME"] = "testserver"
        request.META["SERVER_PORT"] = "80"
        return request

    def _mock_payment(self, payment_id="tr_new123", checkout_url="https://www.mollie.com/checkout/test"):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: payment_id if k == "id" else None
        mock.checkout_url = checkout_url
        return mock

    def _mock_customer(self, customer_id="cst_test123"):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: customer_id if k == "id" else None
        return mock

    def test_first_payment_creates_mandate(self):
        """User exists, no mandate yet — sequenceType=first, redirect to checkout."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.create.return_value = self._mock_customer()
        mock_client.customer_mandates.with_parent_id.return_value.list.return_value = (
            _make_mock_mandates([])
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(self._make_request(), self.obligation, "/return/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://www.mollie.com/checkout/test")

        # MollieCustomer created
        mollie_customer = MollieCustomer.objects.get(user=self.user)
        self.assertEqual(mollie_customer.mollie_customer_id, "cst_test123")

        # MolliePayment created with customer ID
        mollie_payment = MolliePayment.objects.get(mollie_payment_id="tr_new123")
        self.assertEqual(mollie_payment.obligation, self.obligation)
        self.assertEqual(mollie_payment.mollie_customer_id, "cst_test123")

        # Payment created with sequenceType=first
        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["customerId"], "cst_test123")
        self.assertIn("/return/", call_args["redirectUrl"])

    def test_recurring_payment_with_valid_mandate(self):
        """User exists with valid mandate — sequenceType=recurring, redirect to return URL."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_existing")

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customer_mandates.with_parent_id.return_value.list.return_value = (
            _make_mock_mandates([{"status": "valid"}])
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(self._make_request(), self.obligation, "/return/")

        # Redirects to return URL, not Mollie checkout
        self.assertEqual(response.status_code, 302)
        self.assertIn("/return/", response.url)

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "recurring")
        self.assertEqual(call_args["customerId"], "cst_existing")
        self.assertNotIn("redirectUrl", call_args)

    def test_signup_payment_creates_mandate(self):
        """No user (signup flow) — still creates Mollie customer and uses sequenceType=first."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        self.order.ordered_for = None
        self.order.save()

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.create.return_value = self._mock_customer()

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(self._make_request(), self.obligation, "/return/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://www.mollie.com/checkout/test")

        # Mollie customer created via API (but no MollieCustomer record yet — no user to link to)
        mock_client.customers.create.assert_called_once()
        self.assertFalse(MollieCustomer.objects.exists())

        # MolliePayment stores the customer ID for later linking
        mollie_payment = MolliePayment.objects.get(mollie_payment_id="tr_new123")
        self.assertEqual(mollie_payment.mollie_customer_id, "cst_test123")

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["customerId"], "cst_test123")

    def test_first_payment_reuses_existing_customer(self):
        """User with existing MollieCustomer but no mandate — reuses customer, doesn't create new."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_existing")

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customer_mandates.with_parent_id.return_value.list.return_value = (
            _make_mock_mandates([{"status": "invalid"}])
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(self._make_request(), self.obligation, "/return/")

        self.assertEqual(response.status_code, 302)

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["customerId"], "cst_existing")

        # No new customer created
        self.assertEqual(MollieCustomer.objects.count(), 1)
        mock_client.customers.create.assert_not_called()


class LinkMollieCustomerTest(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Mollie Test",
            type="mollie",
            default=True,
        )
        self.mollie_settings = MollieSettings.objects.create(
            payment_provider=self.provider,
            test_api_key="test_xxx",
        )

        self.billing_address = BillingAddress.objects.create(
            user=None,
            name="New Member",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-link",
            name="Link Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order, self.obligation = Order.objects.create_with_obligation(
            product=product,
            billing_address=self.billing_address,
            paid_using=self.provider,
        )

    def test_link_mollie_customer_to_user(self):
        from symfexit.payments.mollie.payments import link_mollie_customer_to_user  # noqa: PLC0415

        MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_signup",
            mollie_customer_id="cst_signup123",
        )

        user = Member.objects.create_user(email="newmember@example.com")
        result = link_mollie_customer_to_user(self.order, user)

        self.assertIsNotNone(result)
        self.assertEqual(result.user, user)
        self.assertEqual(result.mollie_customer_id, "cst_signup123")
        self.assertEqual(MollieCustomer.objects.count(), 1)

    def test_link_skips_when_no_mollie_payment(self):
        from symfexit.payments.mollie.payments import link_mollie_customer_to_user  # noqa: PLC0415

        user = Member.objects.create_user(email="newmember2@example.com")
        result = link_mollie_customer_to_user(self.order, user)

        self.assertIsNone(result)
        self.assertFalse(MollieCustomer.objects.exists())

    def test_link_skips_when_user_already_has_customer(self):
        from symfexit.payments.mollie.payments import link_mollie_customer_to_user  # noqa: PLC0415

        user = Member.objects.create_user(email="existing@example.com")
        existing = MollieCustomer.objects.create(user=user, mollie_customer_id="cst_old")

        MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_signup2",
            mollie_customer_id="cst_new",
        )

        result = link_mollie_customer_to_user(self.order, user)
        self.assertEqual(result, existing)
        self.assertEqual(MollieCustomer.objects.count(), 1)


class ChargeObligationsTest(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Mollie Test",
            type="mollie",
            default=True,
        )
        self.mollie_settings = MollieSettings.objects.create(
            payment_provider=self.provider,
            test_api_key="test_xxx",
            webhook_base_url="https://example.com",
        )

        self.user = Member.objects.create_user(email="charge@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-charge",
            name="Charge Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()

        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")

    def test_charges_obligation_with_valid_mandate(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_charge")

        mock_payment = MagicMock()
        mock_payment.__getitem__ = lambda s, k: "tr_recurring" if k == "id" else None

        mock_client = MagicMock()
        mock_client.customer_mandates.with_parent_id.return_value.list.return_value = (
            _make_mock_mandates([{"status": "valid"}])
        )
        mock_client.payments.create.return_value = mock_payment

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        mollie_payment = MolliePayment.objects.get(mollie_payment_id="tr_recurring")
        self.assertEqual(mollie_payment.obligation, self.obligation)
        self.assertEqual(mollie_payment.mollie_customer_id, "cst_charge")

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "recurring")
        self.assertEqual(call_args["customerId"], "cst_charge")
        self.assertIn("/mollie/webhook/", call_args["webhookUrl"])

    def test_skips_obligation_without_customer(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        charge_obligations()

        self.assertFalse(MolliePayment.objects.exists())

    def test_skips_obligation_without_valid_mandate(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_nomandate")

        mock_client = MagicMock()
        mock_client.customer_mandates.with_parent_id.return_value.list.return_value = (
            _make_mock_mandates([{"status": "invalid"}])
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        self.assertFalse(MolliePayment.objects.exists())

    def test_skips_already_paid_obligations(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_paid")

        from symfexit.payments.models import Transaction  # noqa: PLC0415

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        t = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=bank_account,
            amount_cents=1000,
        )
        Payment.objects.create(
            order=self.order,
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at="2026-01-01T00:00:00Z",
            transaction=t,
        )

        mock_client = MagicMock()

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        self.assertFalse(MolliePayment.objects.exists())
        mock_client.payments.create.assert_not_called()

    def test_skips_cancelled_orders(self):
        from django.utils import timezone as tz  # noqa: PLC0415

        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_cancel")

        self.order.cancelled_at = tz.now()
        self.order.save()

        charge_obligations()

        self.assertFalse(MolliePayment.objects.exists())
