from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.members.admin import Member
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Order,
    Payment,
    PaymentProvider,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
    Transaction,
)
from symfexit.payments.mollie.models import (
    MollieCustomer,
    MolliePayment,
    MollieReversal,
    MollieSettings,
)
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

    def _make_mock_mollie_data(self, status, is_paid, amount="10.00"):
        data = {"status": status, "amount": {"currency": "EUR", "value": amount}}
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: data.get(k)
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

    def test_canceled_does_not_cancel_order(self):
        """A canceled checkout attempt records the status but leaves the order
        active so the user (or charge_obligations) can retry."""
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data("canceled", False)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")

        self.obligation.order.refresh_from_db()
        self.assertIsNone(self.obligation.order.cancelled_at)
        self.mollie_payment.refresh_from_db()
        self.assertEqual(self.mollie_payment.status, "canceled")
        self.assertFalse(Payment.objects.filter(obligation=self.obligation).exists())

    def test_paid_marks_processed_at(self):
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data("paid", True)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")

        self.mollie_payment.refresh_from_db()
        self.assertIsNotNone(self.mollie_payment.processed_at)

    def test_partial_payment(self):
        """Mollie reports €4 paid against a €10 obligation — Payment for €4, no surplus."""
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data(
            "paid", True, amount="4.00"
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")

        payment = Payment.objects.get(obligation=self.obligation)
        self.assertEqual(payment.transaction.amount_cents, 400)

    def test_overpayment_credits_user_account(self):
        """Mollie reports €15 paid against €10 obligation — €10 to obligation, €5 to credit.
        Both amounts are visible as Payments."""
        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data(
            "paid", True, amount="15.00"
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")

        amounts = sorted(
            Payment.objects.filter(obligation=self.obligation).values_list(
                "transaction__amount_cents", flat=True
            )
        )
        self.assertEqual(amounts, [500, 1000])

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.credit_account)
        # Surplus transaction credits the user's credit account
        from symfexit.payments.models import Transaction  # noqa: PLC0415

        credit_txs = Transaction.objects.filter(credit_account=self.user.credit_account)
        self.assertEqual(credit_txs.count(), 1)
        self.assertEqual(credit_txs.first().amount_cents, 500)

    def test_overpayment_when_obligation_already_paid(self):
        """Second Mollie payment of €5 against an already-paid obligation goes
        entirely to credit, but stays visible as a Payment."""
        from symfexit.payments.models import Account, Transaction  # noqa: PLC0415

        # First payment fully covers the obligation.
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        first_tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1000
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=first_tx,
        )

        mock_client = MagicMock()
        mock_client.payments.get.return_value = self._make_mock_mollie_data(
            "paid", True, amount="5.00"
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            self._post_webhook("tr_test123")

        # The surplus gets its own Payment row so it shows up in the admin.
        payments = Payment.objects.filter(obligation=self.obligation).order_by("created_at")
        self.assertEqual(payments.count(), 2)
        self.assertEqual(payments.last().transaction.amount_cents, 500)

        # Surplus is parked in user's credit account.
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.credit_account)
        credit_txs = Transaction.objects.filter(credit_account=self.user.credit_account)
        self.assertEqual(credit_txs.count(), 1)
        self.assertEqual(credit_txs.first().amount_cents, 500)

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


def _make_mock_mollie_data(status, is_paid, amount="10.00"):
    data = {"status": status, "amount": {"currency": "EUR", "value": amount}}
    mock = MagicMock()
    mock.__getitem__ = lambda s, k: data.get(k)
    mock.is_paid.return_value = is_paid
    return mock


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

    def _mock_payment(
        self, payment_id="tr_new123", checkout_url="https://www.mollie.com/checkout/test"
    ):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: payment_id if k == "id" else None
        mock.checkout_url = checkout_url
        return mock

    def _mock_customer(self, customer_id="cst_test123"):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: customer_id if k == "id" else None
        mock.id = customer_id
        return mock

    def _assert_pending_url_carries_return(self, url, expected_return):
        from urllib.parse import parse_qs, urlparse  # noqa: PLC0415

        from symfexit.payments.models import hashids  # noqa: PLC0415

        parsed = urlparse(url)
        eid = hashids.encode(self.obligation.id)
        self.assertIn(f"/mollie/pending/{eid}/", parsed.path)
        self.assertEqual(parse_qs(parsed.query).get("next"), [expected_return])

    def test_first_payment_creates_mandate(self):
        """User exists, no mandate yet — sequenceType=first, redirect to checkout."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.create.return_value = self._mock_customer()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates([])

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(
                self._make_request(), self.obligation, "/return/"
            )

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
        # Mollie's redirectUrl now points to our pending page, which carries the return_url
        self.assertIn("/mollie/pending/", call_args["redirectUrl"])
        self._assert_pending_url_carries_return(call_args["redirectUrl"], "/return/")

    def test_recurring_payment_with_valid_mandate(self):
        """User exists with valid mandate — sequenceType=recurring, redirect via pending page."""
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_existing")

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(
                self._make_request(), self.obligation, "/return/"
            )

        # Redirects to pending page (not Mollie checkout, not directly to return URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mollie/pending/", response.url)
        self._assert_pending_url_carries_return(response.url, "/return/")

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
            response = instance.start_payment_flow(
                self._make_request(), self.obligation, "/return/"
            )

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
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "invalid"}]
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(
                self._make_request(), self.obligation, "/return/"
            )

        self.assertEqual(response.status_code, 302)

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["customerId"], "cst_existing")

        # No new customer created
        self.assertEqual(MollieCustomer.objects.count(), 1)
        mock_client.customers.create.assert_not_called()

    def test_fully_paid_obligation_skips_mollie_and_redirects(self):
        """Obligation already covered (e.g. by member credit) — no Mollie call, no MolliePayment row."""
        from symfexit.payments.models import Account, Payment, Transaction  # noqa: PLC0415
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1550
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        mock_client = MagicMock()
        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            response = instance.start_payment_flow(
                self._make_request(), self.obligation, "/return/"
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/return/", response.url)
        mock_client.payments.create.assert_not_called()
        self.assertFalse(MolliePayment.objects.exists())

    def test_partial_outstanding_charges_remainder(self):
        """€10 already paid via credit on €15.50 obligation — Mollie charges €5.50 remainder."""
        from symfexit.payments.models import Account, Payment, Transaction  # noqa: PLC0415
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_partial")
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1000
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            instance.start_payment_flow(self._make_request(), self.obligation, "/return/")

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["amount"]["value"], "5.50")


class MollieBankAccountChangeTest(TestCase):
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

        self.user = Member.objects.create_user(email="change@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-change",
            name="Change Product",
            price_euros=Decimal("15.50"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()

        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_change")
        self.factory = RequestFactory()

    def _make_request(self):
        request = self.factory.get("/change/")
        request.META["SERVER_NAME"] = "testserver"
        request.META["SERVER_PORT"] = "80"
        return request

    def _mock_payment(
        self, payment_id="tr_change123", checkout_url="https://www.mollie.com/checkout/change"
    ):
        mock = MagicMock()
        mock.__getitem__ = lambda s, k: payment_id if k == "id" else None
        mock.checkout_url = checkout_url
        return mock

    def _start_flow(self, mock_client):
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            instance = MollieProcessorInstance(self.mollie_settings)
            return instance.start_bank_account_change_flow(
                self._make_request(), self.obligation, "/return/"
            )

    def test_keeps_mandates_and_charges_verification_cent(self):
        """A one-cent first payment creates the mandate for the new account;
        existing mandates stay until that payment is paid, so an abandoned
        checkout doesn't leave the member without a mandate."""
        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_customer = mock_client.customers.get.return_value

        response = self._start_flow(mock_client)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://www.mollie.com/checkout/change")

        mock_customer.mandates.delete.assert_not_called()

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["customerId"], "cst_change")
        self.assertEqual(call_args["amount"]["value"], "0.01")
        self.assertIn("/mollie/pending/", call_args["redirectUrl"])
        self.assertTrue(call_args["metadata"]["bank_account_change"])

        mollie_payment = MolliePayment.objects.get(mollie_payment_id="tr_change123")
        self.assertEqual(mollie_payment.obligation, self.obligation)
        self.assertEqual(mollie_payment.mollie_customer_id, "cst_change")

    def test_fully_paid_obligation_still_charges_verification_cent(self):
        """Nothing outstanding — the flow doesn't short-circuit like
        start_payment_flow; the one-cent payment still goes through checkout so
        the new mandate is created."""
        from symfexit.payments.models import Payment, Transaction  # noqa: PLC0415

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1550
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates([])

        response = self._start_flow(mock_client)

        self.assertEqual(response.status_code, 302)
        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["sequenceType"], "first")
        self.assertEqual(call_args["amount"]["value"], "0.01")

    def test_uses_configured_webhook_base_url(self):
        """When webhook_base_url is set (e.g. an ngrok tunnel in development),
        it is used instead of the request's host."""
        self.mollie_settings.webhook_base_url = "https://tunnel.example.com/"
        self.mollie_settings.save()

        mock_client = MagicMock()
        mock_client.payments.create.return_value = self._mock_payment()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates([])

        self._start_flow(mock_client)

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["webhookUrl"], "https://tunnel.example.com/mollie/webhook/")

    def _webhook_client(self, status, is_paid, metadata, mandate_id="mdt_new"):
        data = {
            "status": status,
            "amount": {"currency": "EUR", "value": "0.01"},
            "metadata": metadata,
            "mandateId": mandate_id,
        }
        mollie_data = MagicMock()
        mollie_data.__getitem__ = lambda s, k: data.get(k)
        mollie_data.is_paid.return_value = is_paid

        mock_client = MagicMock()
        mock_client.payments.get.return_value = mollie_data
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [
                {"id": "mdt_old", "status": "valid"},
                {"id": "mdt_old_pending", "status": "pending"},
                {"id": "mdt_invalid", "status": "invalid"},
                {"id": "mdt_new", "status": "valid"},
            ]
        )
        return mock_client

    def _webhook(self, mock_client):
        MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_change123",
            mollie_customer_id="cst_change",
        )
        request = self.factory.post("/mollie/webhook/", {"id": "tr_change123"})
        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            mollie_webhook(request)
            # A repeated webhook doesn't revoke again.
            mollie_webhook(request)

    def test_paid_change_revokes_old_mandates(self):
        mock_client = self._webhook_client("paid", True, {"bank_account_change": True})

        self._webhook(mock_client)

        mock_customer = mock_client.customers.get.return_value
        revoked = [call.args[0] for call in mock_customer.mandates.delete.call_args_list]
        self.assertEqual(revoked, ["mdt_old", "mdt_old_pending"])

    def test_cancelled_or_expired_change_keeps_mandates(self):
        for status in ("canceled", "expired", "failed"):
            with self.subTest(status=status):
                MolliePayment.objects.all().delete()
                mock_client = self._webhook_client(status, False, {"bank_account_change": True})

                self._webhook(mock_client)

                mock_client.customers.get.return_value.mandates.delete.assert_not_called()

    def test_regular_paid_payment_keeps_mandates(self):
        mock_client = self._webhook_client("paid", True, {"obligation_id": "1"})

        self._webhook(mock_client)

        mock_client.customers.get.return_value.mandates.delete.assert_not_called()

    def test_revoke_failure_is_logged(self):
        """A mandate that fails to revoke is logged; the receipt is still recorded."""
        mock_client = self._webhook_client("paid", True, {"bank_account_change": True})
        mock_client.customers.get.return_value.mandates.delete.side_effect = Exception(
            "already revoked"
        )

        with self.assertLogs("symfexit.payments.mollie.payments", level="WARNING"):
            self._webhook(mock_client)

        self.assertIsNotNone(
            MolliePayment.objects.get(mollie_payment_id="tr_change123").processed_at
        )


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
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
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

    def test_future_period_obligation_charged_only_with_now_override(self):
        """A pre-generated obligation for a future period is not charged until
        its period starts; passing `now` simulates the future charge run."""
        from datetime import timedelta  # noqa: PLC0415

        from symfexit.payments.models import Account, Payment, Transaction  # noqa: PLC0415
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_future")

        # Fully pay the current obligation so only the future one is outstanding.
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1000
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        future_now = self.obligation.pay_before + timedelta(days=1)
        future_obligation = self.order.get_or_create_next_payment_obligation(
            timezone="UTC", now=future_now
        )
        self.assertNotEqual(future_obligation.pk, self.obligation.pk)

        mock_payment = MagicMock()
        mock_payment.__getitem__ = lambda s, k: "tr_future" if k == "id" else None
        mock_client = MagicMock()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )
        mock_client.payments.create.return_value = mock_payment

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()
            self.assertFalse(MolliePayment.objects.exists())

            charge_obligations(now=future_now)

        mollie_payment = MolliePayment.objects.get(mollie_payment_id="tr_future")
        self.assertEqual(mollie_payment.obligation, future_obligation)

    def test_skips_obligation_without_customer(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        charge_obligations()

        self.assertFalse(MolliePayment.objects.exists())

    def test_skips_obligation_without_valid_mandate(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_nomandate")

        mock_client = MagicMock()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "invalid"}]
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

    def test_charges_outstanding_remainder_after_credit(self):
        """A €4 credit-funded Payment exists; cron charges the remaining €6."""
        from symfexit.payments.models import Account, Payment, Transaction  # noqa: PLC0415
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_partial")
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=400
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        mock_payment = MagicMock()
        mock_payment.__getitem__ = lambda s, k: "tr_remainder" if k == "id" else None

        mock_client = MagicMock()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )
        mock_client.payments.create.return_value = mock_payment

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        call_args = mock_client.payments.create.call_args[0][0]
        self.assertEqual(call_args["amount"]["value"], "6.00")

    def test_skips_fully_paid_obligation(self):
        """Obligation already fully paid (e.g. by member credit) — no Mollie call."""
        from symfexit.payments.models import Account, Payment, Transaction  # noqa: PLC0415
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_done")
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1000
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        mock_client = MagicMock()
        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        mock_client.payments.create.assert_not_called()

    def test_skips_obligation_with_payment_in_flight(self):
        """A pending direct debit must not be followed by a second one."""
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_inflight")

        mock_client = MagicMock()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )

        for status in MolliePayment.IN_FLIGHT_STATUSES:
            with self.subTest(status=status):
                MolliePayment.objects.all().delete()
                MolliePayment.objects.create(
                    obligation=self.obligation,
                    mollie_payment_id="tr_inflight",
                    mollie_customer_id="cst_inflight",
                    status=status,
                )
                mock_client.payments.get.return_value = _make_mock_mollie_data(status, False)

                with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
                    charge_obligations()

                mock_client.payments.create.assert_not_called()

    def test_missed_paid_webhook_is_booked_instead_of_charging_again(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_missed")
        mp = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_missed_paid",
            mollie_customer_id="cst_missed",
            status="pending",
        )

        mock_client = MagicMock()
        mock_client.payments.get.return_value = _make_mock_mollie_data("paid", True)

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        mock_client.payments.get.assert_called_once_with("tr_missed_paid")
        mock_client.payments.create.assert_not_called()
        mp.refresh_from_db()
        self.assertEqual(mp.status, "paid")
        self.assertIsNotNone(mp.processed_at)
        self.assertTrue(self.obligation.is_fully_paid)

    def test_missed_failed_webhook_charges_again(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_missed")
        mp = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_missed_failed",
            mollie_customer_id="cst_missed",
            status="pending",
        )

        mock_payment = MagicMock()
        mock_payment.__getitem__ = lambda s, k: "tr_after_failed" if k == "id" else None

        mock_client = MagicMock()
        mock_client.payments.get.return_value = _make_mock_mollie_data("failed", False)
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )
        mock_client.payments.create.return_value = mock_payment

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        mp.refresh_from_db()
        self.assertEqual(mp.status, "failed")
        mock_client.payments.create.assert_called_once()
        self.assertTrue(MolliePayment.objects.filter(mollie_payment_id="tr_after_failed").exists())

    def test_charges_again_after_failed_payment(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_retry")
        MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_failed",
            mollie_customer_id="cst_retry",
            status="failed",
        )

        mock_payment = MagicMock()
        mock_payment.__getitem__ = lambda s, k: "tr_retry" if k == "id" else None

        mock_client = MagicMock()
        mock_client.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"status": "valid"}]
        )
        mock_client.payments.create.return_value = mock_payment

        with patch.object(MollieSettings, "get_mollie_client", return_value=mock_client):
            charge_obligations()

        mock_client.payments.create.assert_called_once()
        self.assertTrue(MolliePayment.objects.filter(mollie_payment_id="tr_retry").exists())


class MollieClientTest(TestCase):
    def test_client_is_reused_per_api_key(self):
        settings_a = MollieSettings(test_api_key="test_" + "a" * 30)
        settings_b = MollieSettings(test_api_key="test_" + "b" * 30)

        self.assertIs(settings_a.get_mollie_client(), settings_a.get_mollie_client())
        self.assertIs(
            settings_a.get_mollie_client(),
            MollieSettings(test_api_key="test_" + "a" * 30).get_mollie_client(),
        )
        self.assertIsNot(settings_a.get_mollie_client(), settings_b.get_mollie_client())

    def test_rate_limited_requests_are_retried(self):
        client = MollieSettings(test_api_key="test_" + "c" * 30).get_mollie_client()
        session = requests.Session()
        client._client = session
        client._setup_retry()

        retry = session.get_adapter("https://api.mollie.com").max_retries
        self.assertIn(429, retry.status_forcelist)
        self.assertTrue(retry.is_retry("POST", 429))
        self.assertTrue(retry.respect_retry_after_header)
        del client._client


class RefreshMolliePaymentsTest(TestCase):
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

        self.user = Member.objects.create_user(email="refresh@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-refresh",
            name="Refresh Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()
        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")

    def _make_mollie_payment(self, mollie_id, status, obligation=None):
        return MolliePayment.objects.create(
            obligation=obligation or self.obligation,
            mollie_payment_id=mollie_id,
            status=status,
        )

    def test_missed_webhook_for_signup_payment_is_booked(self):
        """A signup order has no user, so it is never charged, but its payment
        is still refreshed."""
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        signup_billing = BillingAddress.objects.create(
            user=None,
            name="New Member",
            email="new@example.com",
            address="Teststraat 2",
            city="Amsterdam",
            postal_code="1000AA",
        )
        _, signup_obligation = Order.objects.create_with_obligation(
            product=self.order.product,
            billing_address=signup_billing,
            paid_using=self.provider,
            timezone="UTC",
        )
        mp = self._make_mollie_payment("tr_signup", "open", obligation=signup_obligation)

        client = MagicMock()
        client.payments.get.return_value = _make_mock_mollie_data("paid", True)

        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            charge_obligations()

        mp.refresh_from_db()
        self.assertEqual(mp.status, "paid")
        self.assertIsNotNone(mp.processed_at)
        self.assertTrue(signup_obligation.is_fully_paid)

    def test_skips_terminal_status(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        self._make_mollie_payment("tr_done", status="paid")

        client = MagicMock()
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            charge_obligations()

        client.payments.get.assert_not_called()

    def test_refresh_error_does_not_stop_other_payments(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        self._make_mollie_payment("tr_broken", "pending")
        good = self._make_mollie_payment("tr_good", "pending")

        def get(payment_id):
            if payment_id == "tr_broken":
                raise RuntimeError("Mollie unavailable")
            return _make_mock_mollie_data("failed", False)

        client = MagicMock()
        client.payments.get.side_effect = get

        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            charge_obligations()

        good.refresh_from_db()
        self.assertEqual(good.status, "failed")
        # tr_broken still looks in flight, so no new charge was made.
        client.payments.create.assert_not_called()


class BackfillProcessedAtMigrationTest(TestCase):
    """Sanity check that future MolliePayments with terminal status created
    pre-migration get backfilled — exercised here by stamping processed_at=None
    on a paid row and verifying a refresh doesn't re-record receipt."""

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
        self.user = Member.objects.create_user(email="legacy@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-legacy",
            name="Legacy Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()
        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")

    def test_processed_marker_blocks_double_record(self):
        """A paid MolliePayment with processed_at set must not re-create receipt rows."""
        from symfexit.payments.models import Account, Transaction  # noqa: PLC0415
        from symfexit.payments.mollie.views import _refresh_from_mollie  # noqa: PLC0415

        # Simulate a row processed under old code: Payment exists, processed_at is set
        # (representing what the new backfill migration produces).
        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        first_tx = Transaction.objects.create(
            credit_account=ar_account, debit_account=bank_account, amount_cents=1000
        )
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=first_tx,
        )
        mp = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_legacy",
            status="paid",
            processed_at=timezone.now(),
        )

        client = MagicMock()
        client.payments.get.return_value = self._mock_data()

        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            _refresh_from_mollie(mp)

        # Still exactly one Payment, no phantom credit transaction.
        self.assertEqual(Payment.objects.filter(obligation=self.obligation).count(), 1)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.credit_account)

    def _mock_data(self):
        mock = MagicMock()
        payload = {"status": "paid", "amount": {"currency": "EUR", "value": "10.00"}}
        mock.__getitem__ = lambda s, k: payload.get(k)
        mock.is_paid.return_value = True
        return mock


class MolliePendingViewTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
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
        self.user = Member.objects.create_user(email="pending@example.com")
        self.billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-pending",
            name="Pending Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.order = product.order(for_user=self.user, billing_address=self.billing_address)
        self.order.paid_using = self.provider
        self.order.save()
        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")

    def _eid(self):
        from symfexit.payments.models import hashids  # noqa: PLC0415

        return hashids.encode(self.obligation.id)

    def _pending_url(self, return_url="/return/"):
        from urllib.parse import urlencode  # noqa: PLC0415

        return f"/mollie/pending/{self._eid()}/?{urlencode({'next': return_url})}"

    def _status_url(self):
        return f"/mollie/pending/{self._eid()}/status/"

    @override_settings(LANGUAGE_CODE="en-US", LANGUAGES=(("en", "English"),))
    def test_pending_renders(self):
        response = self.client.get(self._pending_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Processing", response.content)

    def test_pending_rejects_external_next(self):
        response = self.client.get(self._pending_url("https://evil.example.com/"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"https://evil.example.com/", response.content)

    def test_pending_rejects_unknown_eid(self):
        response = self.client.get("/mollie/pending/not-a-real-eid/")
        self.assertEqual(response.status_code, 404)

    def test_status_rejects_unknown_eid(self):
        response = self.client.get("/mollie/pending/not-a-real-eid/status/")
        self.assertEqual(response.status_code, 404)

    def _mock_mollie_client(self, status, is_paid, amount="10.00"):
        client = MagicMock()
        data = MagicMock()
        payload = {"status": status, "amount": {"currency": "EUR", "value": amount}}
        data.__getitem__ = lambda s, k: payload.get(k)
        data.is_paid.return_value = is_paid
        client.payments.get.return_value = data
        return client

    def test_status_returns_open_when_mollie_says_open(self):
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_open", status="open"
        )
        client = self._mock_mollie_client("open", False)
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            response = self.client.get(self._status_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"done": False})
        client.payments.get.assert_called_once_with("tr_open")

    def test_status_refresh_promotes_open_to_paid(self):
        """Webhook missed: status endpoint pulls 'paid' from Mollie and creates Payment."""
        mollie_payment = MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_late", status="open"
        )
        client = self._mock_mollie_client("paid", True)
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            response = self.client.get(self._status_url())
        self.assertEqual(response.json(), {"done": True})
        mollie_payment.refresh_from_db()
        self.assertEqual(mollie_payment.status, "paid")
        self.assertTrue(Payment.objects.filter(obligation=self.obligation).exists())

    def test_status_refresh_does_not_cancel_order_when_canceled(self):
        """A canceled checkout marks status=canceled but leaves the order
        active; the front-end stops polling but the user can retry."""
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_cancel", status="open"
        )
        client = self._mock_mollie_client("canceled", False)
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            response = self.client.get(self._status_url())
        self.assertEqual(response.json(), {"done": True})
        self.obligation.order.refresh_from_db()
        self.assertIsNone(self.obligation.order.cancelled_at)

    def test_status_returns_done_after_webhook(self):
        """Webhook already updated status — no Mollie call needed."""
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_paid", status="paid"
        )
        with patch.object(MollieSettings, "get_mollie_client") as mocked:
            response = self.client.get(self._status_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"done": True})
        mocked.assert_not_called()

    def test_status_returns_done_when_failed(self):
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_fail", status="failed"
        )
        with patch.object(MollieSettings, "get_mollie_client") as mocked:
            response = self.client.get(self._status_url())
        self.assertEqual(response.json(), {"done": True})
        mocked.assert_not_called()

    def test_status_with_no_mollie_payment(self):
        response = self.client.get(self._status_url())
        self.assertEqual(response.json(), {"done": False})

    def test_status_uses_latest_mollie_payment(self):
        from datetime import timedelta  # noqa: PLC0415

        from django.utils import timezone as tz  # noqa: PLC0415

        older = MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_old", status="failed"
        )
        MolliePayment.objects.filter(pk=older.pk).update(created_at=tz.now() - timedelta(minutes=5))
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_new", status="open"
        )

        client = self._mock_mollie_client("open", False)
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            response = self.client.get(self._status_url())
        self.assertEqual(response.json(), {"done": False})
        client.payments.get.assert_called_once_with("tr_new")

    def test_status_swallows_mollie_errors(self):
        """If Mollie API call fails, fall back to local status (still 'open')."""
        MolliePayment.objects.create(
            obligation=self.obligation, mollie_payment_id="tr_err", status="open"
        )
        client = MagicMock()
        client.payments.get.side_effect = RuntimeError("network down")
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            response = self.client.get(self._status_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"done": False})


def _make_paid_mollie_data(amount="10.00", chargebacks=(), refunds=()):
    mock = _make_mock_mollie_data("paid", True, amount)
    mock.has_chargebacks.return_value = bool(chargebacks)
    mock.chargebacks.list.return_value = list(chargebacks)
    mock.has_refunds.return_value = bool(refunds)
    mock.refunds.list.return_value = list(refunds)
    return mock


def _mollie_page(items):
    page = MagicMock()
    page.__iter__.side_effect = lambda: iter(items)
    page.has_next.return_value = False
    return page


def _chargeback(reversed_at=None, amount="10.00"):
    return {
        "id": "chb_1",
        "paymentId": "tr_paid",
        "amount": {"currency": "EUR", "value": amount},
        "createdAt": timezone.now().isoformat(),
        "reversedAt": reversed_at,
    }


def _refund(status, amount="10.00"):
    return {
        "id": "re_1",
        "paymentId": "tr_paid",
        "amount": {"currency": "EUR", "value": amount},
        "status": status,
        "createdAt": timezone.now().isoformat(),
    }


class _MollieReversalTestCase(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        self.bank_account, _ = Account.get_bank_account()
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

        self.user = Member.objects.create_user(email="reversal@example.com")
        billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Test User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-mollie-reversal",
            name="Reversal Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)
        self.order = product.order(for_user=self.user, billing_address=billing_address)
        self.order.paid_using = self.provider
        self.order.save()
        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")
        MollieCustomer.objects.create(user=self.user, mollie_customer_id="cst_1")
        self.mollie_payment = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_paid",
            mollie_customer_id="cst_1",
        )

        self.api = MagicMock()
        self.api.customers.get.return_value.mandates.list.return_value = _make_mock_mandates(
            [{"id": "mdt_1", "status": "valid"}]
        )
        self.api.chargebacks.list.return_value = _mollie_page([])
        self.api.refunds.list.return_value = _mollie_page([])

    def _webhook(self, mollie_data):
        self.api.payments.get.return_value = mollie_data
        request = RequestFactory().post("/mollie/webhook/", {"id": "tr_paid"})
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            response = mollie_webhook(request)
        self.assertEqual(response.status_code, 200)


class MollieReversalTest(_MollieReversalTestCase):
    def test_receipt_is_linked_to_its_payment(self):
        self._webhook(_make_paid_mollie_data())

        self.assertEqual(list(self.mollie_payment.payments.all()), [Payment.objects.get()])

    def test_chargeback_cancels_order_and_revokes_mandate(self):
        from symfexit.payments.models import CancellationReason, PaymentReversal  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())
        self._webhook(_make_paid_mollie_data(chargebacks=[_chargeback()]))

        reversal = PaymentReversal.objects.get()
        self.assertEqual(reversal.reason, PaymentReversal.Reason.CHARGEBACK)
        self.assertEqual(reversal.mollie_reversals.get().mollie_id, "chb_1")
        self.assertEqual(self.obligation.outstanding_cents, 1000)
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancellation_reason, CancellationReason.CHARGEBACK)
        self.api.customers.get.return_value.mandates.delete.assert_called_once_with("mdt_1")

        # Mollie calling again books nothing new.
        self._webhook(_make_paid_mollie_data(chargebacks=[_chargeback()]))
        self.assertEqual(PaymentReversal.objects.count(), 1)
        self.api.customers.get.return_value.mandates.delete.assert_called_once()

    def test_reversed_chargeback_books_the_money_again(self):
        self._webhook(_make_paid_mollie_data())
        self._webhook(_make_paid_mollie_data(chargebacks=[_chargeback()]))
        self._webhook(
            _make_paid_mollie_data(
                chargebacks=[_chargeback(reversed_at=timezone.now().isoformat())]
            )
        )

        self.assertTrue(self.obligation.is_fully_paid)
        self.assertEqual(self.bank_account.balance_cents(), 1000)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.cancelled_at)

    def test_refund_is_booked_once_refunded(self):
        from symfexit.payments.models import PaymentReversal  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())
        self._webhook(_make_paid_mollie_data(refunds=[_refund("pending")]))

        self.assertFalse(PaymentReversal.objects.exists())
        self.assertEqual(MollieReversal.objects.get().status, "pending")

        self._webhook(_make_paid_mollie_data(refunds=[_refund("refunded")]))

        reversal = PaymentReversal.objects.get()
        self.assertEqual(reversal.reason, PaymentReversal.Reason.REFUND)
        self.assertEqual(reversal.mollie_reversals.get().mollie_id, "re_1")
        self.assertTrue(self.obligation.is_fully_paid)
        self.assertEqual(self.bank_account.balance_cents(), 0)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.cancelled_at)

    def test_processor_refund_starts_mollie_refund(self):
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())
        payment = Payment.objects.get()
        instance = MollieProcessorInstance(self.mollie_settings)
        self.assertEqual(instance.refundable_cents(payment), 1000)

        api_payment = MagicMock()
        api_payment.refunds.create.return_value = _refund("pending")
        self.api.payments.get.return_value = api_payment
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            instance.refund(payment)

        api_payment.refunds.create.assert_called_once_with(
            {"amount": {"currency": "EUR", "value": "10.00"}}
        )
        self.assertEqual(MollieReversal.objects.get().status, "pending")
        # The pending refund already claims the money; it can't be refunded twice.
        self.assertEqual(instance.refundable_cents(payment), 0)

    def test_payment_from_member_credit_is_not_refundable_online(self):
        from symfexit.payments.mollie.payments import MollieProcessorInstance  # noqa: PLC0415

        credit_payment = Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=Transaction.objects.create(
                credit_account=Account.get_accounts_receivable_account()[0],
                debit_account=self.bank_account,
                amount_cents=1000,
            ),
        )
        instance = MollieProcessorInstance(self.mollie_settings)
        self.assertEqual(instance.refundable_cents(credit_payment), 0)

    def test_sweep_catches_missed_chargeback(self):
        from symfexit.payments.models import CancellationReason  # noqa: PLC0415
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())

        self.api.chargebacks.list.return_value = _mollie_page([_chargeback()])
        self.api.payments.get.return_value = _make_paid_mollie_data(chargebacks=[_chargeback()])
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            charge_obligations()

        self.order.refresh_from_db()
        self.assertEqual(self.order.cancellation_reason, CancellationReason.CHARGEBACK)

    def test_sweep_skips_reversals_already_booked(self):
        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())
        self._webhook(_make_paid_mollie_data(chargebacks=[_chargeback()]))
        self.api.payments.get.reset_mock()

        self.api.chargebacks.list.return_value = _mollie_page([_chargeback()])
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            charge_obligations()

        self.api.payments.get.assert_not_called()

    def test_sweep_stops_at_lookback(self):
        from datetime import timedelta  # noqa: PLC0415

        from symfexit.payments.tasks import charge_obligations  # noqa: PLC0415

        self._webhook(_make_paid_mollie_data())
        self.api.payments.get.reset_mock()

        old = {**_chargeback(), "createdAt": (timezone.now() - timedelta(days=500)).isoformat()}
        self.api.chargebacks.list.return_value = _mollie_page([old])
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            charge_obligations()

        self.api.payments.get.assert_not_called()

    def test_migration_links_existing_payments(self):
        """Rows booked before MolliePayment.payments existed get linked to
        their receipt, not to a credit-funded Payment on the same obligation."""
        import importlib  # noqa: PLC0415

        from django.apps import apps  # noqa: PLC0415

        migration = importlib.import_module(
            "symfexit.payments.mollie.migrations.0002_molliepayment_payments_molliereversal"
        )

        credit_account = self.user.get_or_create_credit_account()
        Payment.objects.create(
            obligation=self.obligation,
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=Transaction.objects.create(
                credit_account=Account.get_accounts_receivable_account()[0],
                debit_account=credit_account,
                amount_cents=300,
            ),
        )
        # €9 against the €7 still outstanding: €7 applied, €2 surplus.
        self._webhook(_make_paid_mollie_data(amount="9.00"))
        receipt = set(self.mollie_payment.payments.all())
        self.assertEqual(len(receipt), 2)
        self.mollie_payment.payments.clear()

        migration.link_payments(apps, None)

        self.assertEqual(set(self.mollie_payment.payments.all()), receipt)


class PaymentRefundAdminActionTest(_MollieReversalTestCase):
    """Runs the refund action against the same fixtures."""

    def _admin_request(self, data):
        from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: PLC0415

        request = RequestFactory().post("/admin/payments/payment/", data)
        request.user = Member.objects.create_superuser(email="admin@example.com", password="x")
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _run_action(self, data):
        from django.contrib import admin as django_admin  # noqa: PLC0415

        model_admin = django_admin.site._registry[Payment]
        request = self._admin_request(data)
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.api):
            return model_admin.refund_selected(request, Payment.objects.all())

    def _setup_payments(self):
        self._webhook(_make_paid_mollie_data())
        mollie_paid = Payment.objects.get()
        waived = Payment.objects.create(
            obligation=self.obligation,
            paid_using=None,
            paid_at=timezone.now(),
            transaction=Transaction.objects.create(
                credit_account=Account.get_accounts_receivable_account()[0],
                debit_account=Account.get_waived_account()[0],
                amount_cents=500,
            ),
        )
        return mollie_paid, waived

    def test_confirmation_lists_refundable_and_skipped_payments(self):
        mollie_paid, waived = self._setup_payments()

        response = self._run_action({})

        self.assertEqual(
            [row["payment"] for row in response.context_data["refundable"]], [mollie_paid]
        )
        self.assertEqual(
            [row["payment"] for row in response.context_data["not_refundable"]], [waived]
        )
        self.assertEqual(response.context_data["refundable_total"], "10.00")
        self.api.payments.get.return_value.refunds.create.assert_not_called()

    def test_confirming_starts_refunds(self):
        self._setup_payments()
        api_payment = MagicMock()
        api_payment.refunds.create.return_value = _refund("pending")
        self.api.payments.get.return_value = api_payment

        response = self._run_action({"post": "yes"})

        self.assertIsNone(response)
        api_payment.refunds.create.assert_called_once()
        self.assertEqual(MollieReversal.objects.get().status, "pending")


@override_settings(LANGUAGE_CODE="en-US", LANGUAGES=(("en", "English"),))
class PaymentRefundAdminPageTest(FastTenantTestCase):
    """The refund flow through the real admin pages."""

    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        provider = PaymentProvider.objects.create(name="Mollie Test", type="mollie", default=True)
        MollieSettings.objects.create(payment_provider=provider, test_api_key="test_xxx")
        user = Member.objects.create_user(email="page@example.com")
        billing_address = BillingAddress.objects.create(
            user=user,
            name="Page User",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        product = Product.objects.create(
            enabled=True,
            sku="test-refund-page",
            name="Refund Page Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)
        self.order = product.order(for_user=user, billing_address=billing_address)
        self.order.paid_using = provider
        self.order.save()
        self.obligation = self.order.get_or_create_next_payment_obligation(timezone="UTC")

        from symfexit.payments.services import record_receipt  # noqa: PLC0415

        self.payment = record_receipt(self.obligation, 1000)
        self.mollie_payment = MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_page",
            status="paid",
            processed_at=timezone.now(),
        )
        self.mollie_payment.payments.add(self.payment)

        admin_user = Member.objects.create_superuser(email="page-admin@example.com", password="x")
        self.client.force_login(admin_user)

    def test_admin_pages_render(self):
        for url in (
            "/admin/payments/payment/",
            f"/admin/payments/payment/{self.payment.pk}/change/",
            "/admin/payments/order/",
            f"/admin/payments/order/{self.order.pk}/change/",
            f"/admin/payments/paymentobligation/{self.obligation.pk}/change/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_obligation_page_shows_pending_refund(self):
        MollieReversal.objects.create(
            mollie_payment=self.mollie_payment,
            mollie_id="re_page",
            kind=MollieReversal.Kind.REFUND,
            amount_cents=1000,
            status="pending",
        )

        response = self.client.get(
            f"/admin/payments/paymentobligation/{self.obligation.pk}/change/"
        )

        self.assertContains(response, "re_page: refund of €10.00, pending")

    def test_refund_action_shows_confirmation(self):
        response = self.client.post(
            "/admin/payments/payment/",
            {"action": "refund_selected", "_selected_action": [self.payment.pk]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["refundable_total"], "10.00")
        self.assertContains(response, "10.00")
        self.assertContains(response, 'name="post" value="yes"')
