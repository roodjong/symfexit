from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.members.views import _start_payment
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.models import (
    Account,
    Order,
    PaymentProvider,
    PeriodUnit,
    Product,
    ProductType,
    Subscription,
)

User = get_user_model()


class MembersPageTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        # Log in a test user
        self.client.force_login(User.objects.create_superuser(email="testuser@example.com"))

    def test_members_page_loads(self):
        response = self.client.get("/admin/members/member/")
        self.assertEqual(response.status_code, 200)

    def test_members_filters_loads(self):
        response = self.client.get(
            "/admin/members/member/",
            {
                "cadre__exact": 1,
                "is_active": "N",
                "is_staff__exact": 0,
                "is_superuser__exact": 1,
                "permission_group": 1,
            },
        )
        self.assertEqual(response.status_code, 200)


class StartPaymentDeduplicationTest(TestCase):
    def setUp(self):
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()

        self.provider = PaymentProvider.objects.create(
            name="Test provider", type="mollie", default=True
        )

        self.product = Product.objects.create(
            enabled=True,
            sku="membership-standard",
            name="Membership (Standard)",
            price_euros=Decimal("10.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=self.product, period_unit=PeriodUnit.MONTH, period=1)
        membership_type = MembershipType.objects.create(name="Standard", slug="standard")
        tier = MembershipTier.objects.create(
            membership_type=membership_type, name="Standard", product=self.product
        )

        self.user = User.objects.create_user(email="dedup@example.com")
        self.user.membership_tier = tier
        self.user.address = "Teststraat 1"
        self.user.city = "Amsterdam"
        self.user.postal_code = "1000AA"
        self.user.save()

        self.factory = RequestFactory()

    def _start_payment(self):
        request = self.factory.post("/payment/start")
        request.user = self.user
        instance = MagicMock()
        instance.start_payment_flow.return_value = HttpResponse()
        with patch(
            "symfexit.members.views.payments_registry.get_instance_for_provider",
            return_value=instance,
        ):
            _start_payment(request)

    def test_repeated_start_reuses_active_order(self):
        self._start_payment()
        self._start_payment()
        self._start_payment()

        active = Order.objects.filter(ordered_for=self.user, cancelled_at__isnull=True)
        self.assertEqual(active.count(), 1)

    def test_new_tier_cancels_previous_order(self):
        self._start_payment()

        other_product = Product.objects.create(
            enabled=True,
            sku="membership-plus",
            name="Membership (Plus)",
            price_euros=Decimal("15.00"),
            type=ProductType.SUBSCRIPTION,
        )
        Subscription.objects.create(product=other_product, period_unit=PeriodUnit.MONTH, period=1)
        other_tier = MembershipTier.objects.create(
            membership_type=self.user.membership_tier.membership_type,
            name="Plus",
            product=other_product,
        )
        self.user.membership_tier = other_tier
        self.user.save()

        self._start_payment()

        active = Order.objects.filter(ordered_for=self.user, cancelled_at__isnull=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().product, other_product)
        self.assertEqual(
            Order.objects.filter(ordered_for=self.user, cancelled_at__isnull=False).count(), 1
        )
