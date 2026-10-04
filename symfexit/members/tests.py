from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.members.views import _start_payment
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.models import (
    Account,
    BillingAddress,
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

    def test_cancel_membership_admin_action_cancels_user(self):
        member = User.objects.create_user(
            email="member@example.com",
            password="password",
            member_identifier=1001,
            first_name="Jane",
            last_name="Doe",
        )

        response = self.client.post(
            reverse("admin:members_member_cancel_membership", args=[member.pk])
        )

        member.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(member.is_active)
        self.assertIsNotNone(member.date_left)


class AmountChangeTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        Account.get_accounts_receivable_account()
        Account.get_bank_account()
        Account.get_revenue_account()
        provider = PaymentProvider.objects.create(name="Test", type="mollie", default=True)

        self.membership_type = MembershipType.objects.create(name="Standard", slug="standard")
        self.products = []
        for sku, price in (("basic", "10.00"), ("plus", "20.00")):
            product = Product.objects.create(
                enabled=True,
                sku=sku,
                name=sku,
                price_euros=Decimal(price),
                type=ProductType.SUBSCRIPTION,
            )
            Subscription.objects.create(product=product, period_unit=PeriodUnit.MONTH, period=1)
            self.products.append(product)
        self.tiers = [
            MembershipTier.objects.create(
                membership_type=self.membership_type, name=p.name, product=p
            )
            for p in self.products
        ]

        self.user = User.objects.create_user(
            email="member@example.com", password="password", member_identifier=2001
        )
        self.user.membership_type = self.membership_type
        self.user.membership_tier = self.tiers[0]
        self.user.save()
        self.client.force_login(self.user)
        billing_address = BillingAddress.objects.create(
            user=self.user,
            name="Member",
            address="Street 1",
            city="Amsterdam",
            postal_code="1000AA",
        )
        self.order, _ = Order.objects.create_with_obligation(
            product=self.products[0],
            paid_using=provider,
            billing_address=billing_address,
            for_user=self.user,
        )

    def test_page_loads(self):
        response = self.client.get(reverse("members:amount-change"))
        self.assertEqual(response.status_code, 200)

    def test_changes_price_of_active_order(self):
        response = self.client.post(
            reverse("members:amount-change"),
            {
                "membership_type": self.membership_type.pk,
                "payment_tier": str(self.tiers[1].pk),
            },
        )
        self.assertRedirects(response, reverse("members:memberdata"), fetch_redirect_response=False)
        self.order.refresh_from_db()
        self.assertEqual(self.order.product_price_euros, Decimal("20.00"))
        self.assertEqual(self.order.product_id, self.products[1].pk)

    def test_redirects_without_active_order(self):
        self.order.cancel()
        response = self.client.get(reverse("members:amount-change"))
        self.assertRedirects(response, reverse("members:memberdata"), fetch_redirect_response=False)

    def test_current_tier_preselected(self):
        response = self.client.get(reverse("members:amount-change"))
        self.assertEqual(response.context["form"].initial["payment_tier"], str(self.tiers[0].pk))

    def test_unmatched_price_falls_back_to_custom(self):
        self.membership_type.allow_custom_amount = True
        self.membership_type.save()
        self.order.product_price_euros = Decimal("15.00")
        self.order.save()
        response = self.client.get(reverse("members:amount-change"))
        initial = response.context["form"].initial
        self.assertEqual(initial["payment_tier"], "custom")
        self.assertEqual(initial["pay_more"], Decimal("15.00"))


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
