from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.test import RequestFactory
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

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
from symfexit.signup.admin import MembershipApplicationAdmin
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


class MembershipApplicationAdminTest(FastTenantTestCase):
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
            sku="signup-admin-product",
            name="Signup Admin Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=1)

        self.admin = MembershipApplicationAdmin(model=MembershipApplication, admin_site=admin.site)
        self.request = RequestFactory().get("/admin/signup/membershipapplication/")

    def _create_application(self, **overrides):
        defaults = {
            "first_name": "Test",
            "last_name": "User",
            "email": "signup-admin@example.com",
            "phone_number": "+31600000000",
            "birth_date": date(2000, 1, 1),
            "address": "Teststraat 1",
            "city": "Amsterdam",
            "postal_code": "1000AA",
            "payment_amount_euros": Decimal("10.00"),
        }
        defaults.update(overrides)
        return MembershipApplication.objects.create(**defaults)

    def _create_order_for_application(self, application):
        billing = BillingAddress.objects.create(
            user=None,
            name=f"{application.first_name} {application.last_name}",
            email=application.email,
            address=application.address,
            city=application.city,
            postal_code=application.postal_code,
        )
        order, obligation = Order.objects.create_with_obligation(
            product=self.product,
            billing_address=billing,
            price_euros=Decimal("10.00"),
            paid_using=self.provider,
        )
        application._order = order
        application.save(update_fields=["_order"])
        return order, obligation

    def test_queryset_annotations_report_paid_status(self):
        self._create_application(email="unpaid@example.com")
        paid_application = self._create_application(email="paid@example.com")
        self._create_order_for_application(paid_application)

        from django.utils import timezone  # noqa: PLC0415

        ar_account, _ = Account.get_accounts_receivable_account()
        bank_account, _ = Account.get_bank_account()
        tx = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=bank_account,
            amount_cents=1000,
        )
        Payment.objects.create(
            obligation=paid_application._order.paymentobligation_set.get(),
            paid_using=self.provider,
            paid_at=timezone.now(),
            transaction=tx,
        )

        queryset = self.admin.get_queryset(self.request)
        totals = {
            email: (payment_total, order_price)
            for email, payment_total, order_price in queryset.values_list(
                "email", "payment_total", "order_price"
            )
        }

        self.assertEqual(totals["unpaid@example.com"], (0, None))
        self.assertEqual(totals["paid@example.com"], (1000, Decimal("10.00")))


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


class RejectApplicationRefundTest(FastTenantTestCase):
    def setUp(self):
        from symfexit.payments.mollie.models import MolliePayment, MollieSettings  # noqa: PLC0415
        from symfexit.payments.services import record_receipt  # noqa: PLC0415

        super().setUp()
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(name="Mollie", type="mollie", default=True)
        MollieSettings.objects.create(payment_provider=self.provider, test_api_key="test_xxx")
        product = Product.objects.create(
            enabled=True,
            sku="reject-product",
            name="Reject Product",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)

        self.application = MembershipApplication.objects.create(
            first_name="Rejected",
            last_name="Applicant",
            email="rejected@example.com",
            phone_number="+31600000000",
            birth_date=date(2000, 1, 1),
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
            payment_amount_euros=Decimal("10.00"),
        )
        billing = BillingAddress.objects.create(
            user=None,
            name="Rejected Applicant",
            email="rejected@example.com",
            address="Teststraat 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        self.order, self.obligation = Order.objects.create_with_obligation(
            product=product, billing_address=billing, paid_using=self.provider
        )
        self.application._order = self.order
        self.application.save(update_fields=["_order"])

        self.payment = record_receipt(self.obligation, 1000)
        MolliePayment.objects.create(
            obligation=self.obligation,
            mollie_payment_id="tr_signup",
            status="paid",
            processed_at=self.payment.created_at,
        ).payments.add(self.payment)

    def _reject(self):
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: PLC0415

        from symfexit.payments.mollie.models import MollieSettings  # noqa: PLC0415

        self.api_payment = MagicMock()
        self.api_payment.refunds.create.return_value = {
            "id": "re_signup",
            "amount": {"currency": "EUR", "value": "10.00"},
            "status": "pending",
        }
        client = MagicMock()
        client.payments.get.return_value = self.api_payment

        request = RequestFactory().post("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        model_admin = MembershipApplicationAdmin(model=MembershipApplication, admin_site=admin.site)
        self.application.status = MembershipApplication.Status.REJECTED
        with patch.object(MollieSettings, "get_mollie_client", return_value=client):
            model_admin.save_model(request, self.application, form=None, change=True)
        return [str(m) for m in request._messages]

    def test_rejecting_refunds_payment_and_cancels_order(self):
        from symfexit.payments.models import CancellationReason  # noqa: PLC0415
        from symfexit.payments.mollie.models import MollieReversal  # noqa: PLC0415

        messages = self._reject()

        self.api_payment.refunds.create.assert_called_once_with(
            {"amount": {"currency": "EUR", "value": "10.00"}}
        )
        self.assertEqual(MollieReversal.objects.get().status, "pending")
        self.order.refresh_from_db()
        self.assertEqual(self.order.cancellation_reason, CancellationReason.SIGNUP_REJECTED)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, MembershipApplication.Status.REJECTED)
        self.assertEqual(len(messages), 1)

    def test_payment_that_cannot_be_refunded_online_is_reported(self):
        Payment.objects.filter(pk=self.payment.pk).update(paid_using=None)

        messages = self._reject()

        self.api_payment.refunds.create.assert_not_called()
        self.assertEqual(len(messages), 1)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.cancelled_at)

    def test_rejecting_without_order_does_nothing(self):
        self.application._order = None
        self.application.save(update_fields=["_order"])

        self.assertEqual(self._reject(), [])
