"""Tests for the cancel_mijnrood_subscriptions management command."""

import csv
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django_tenants.test.cases import FastTenantTestCase
from mollie.api.error import NotFoundError, ResponseError

from symfexit.payments.models import Account, PaymentProvider
from symfexit.payments.mollie.models import MollieSettings

MEMBER_FIELDS = [
    "id", "first_name", "last_name", "email", "mollie_customer_id", "mollie_subscription_id",
]


class CancelMijnroodSubscriptionsTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.export_dir = Path(tmp.name)

        self.write_csv(
            "admin_member",
            [
                # active subscription -> cancelled
                {
                    "id": "10", "first_name": "Piet", "last_name": "Jansen",
                    "mollie_customer_id": "cst_piet", "mollie_subscription_id": "sub_active",
                },
                # customer no longer exists at Mollie -> reported, not a failure
                {
                    "id": "11", "first_name": "Anna", "last_name": "Berg",
                    "mollie_customer_id": "cst_anna", "mollie_subscription_id": "sub_gone",
                },
                # no subscription -> ignored
                {"id": "12", "first_name": "Kees", "last_name": "Vries"},
                # subscription without customer id -> manual-action warning
                {
                    "id": "13", "first_name": "Dirk", "last_name": "Los",
                    "mollie_subscription_id": "sub_nocust",
                },
            ],
        )
        self.write_csv(
            "admin_support_member",
            [
                # already cancelled at Mollie -> skipped
                {
                    "id": "1", "first_name": "Sofie", "last_name": "Bakker",
                    "mollie_customer_id": "cst_sofie", "mollie_subscription_id": "sub_done",
                },
            ],
        )

        self.provider = PaymentProvider.objects.create(
            name="Mollie", type="mollie", credit_to_account=Account.get_bank_account()[0]
        )
        MollieSettings.objects.create(
            payment_provider=self.provider, test_api_key="test_123", live_mode=False
        )

        self.customers = {}
        statuses = {"cst_piet": {"sub_active": "active"}, "cst_sofie": {"sub_done": "canceled"}}

        def customers_get(customer_id):
            if customer_id == "cst_anna":
                raise NotFoundError({"detail": "Customer not found", "status": 404})
            if customer_id not in self.customers:
                customer = MagicMock()
                customer.subscriptions.get.side_effect = lambda sid: MagicMock(
                    status=statuses[customer_id][sid]
                )
                self.customers[customer_id] = customer
            return self.customers[customer_id]

        self.client = MagicMock()
        self.client.customers.get.side_effect = customers_get

    def write_csv(self, table, rows):
        with (self.export_dir / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MEMBER_FIELDS, restval="")
            writer.writeheader()
            writer.writerows(rows)

    def run_command(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(MollieSettings, "get_mollie_client", return_value=self.client):
            call_command(
                "cancel_mijnrood_subscriptions",
                str(self.export_dir),
                *args,
                stdout=stdout,
                stderr=stderr,
            )
        return stdout.getvalue(), stderr.getvalue()

    def test_cancels_active_subscriptions(self):
        stdout, stderr = self.run_command()
        self.customers["cst_piet"].subscriptions.delete.assert_called_once_with("sub_active")
        self.assertIn(f"Using Mollie provider 'Mollie' (id {self.provider.pk}, test mode)", stdout)
        self.assertIn("cancelled sub_active", stdout)
        self.assertIn("cancelled: 1", stdout)
        self.assertIn("already inactive: 1", stdout)
        self.assertIn("not found at Mollie: 1", stdout)
        self.assertIn("sub_done already canceled", stdout)
        self.assertIn("cst_anna/sub_gone not found", stdout)
        self.assertIn("cancel it manually", stderr)
        self.assertNotIn("different Mollie account", stderr)

    def test_already_cancelled_is_not_deleted(self):
        self.run_command()
        self.customers["cst_sofie"].subscriptions.delete.assert_not_called()

    def test_dry_run_does_not_cancel(self):
        stdout, _ = self.run_command("--dry-run")
        self.customers["cst_piet"].subscriptions.delete.assert_not_called()
        self.assertIn("would cancel sub_active (active)", stdout)
        self.assertIn("would be cancelled: 1", stdout)

    def test_requires_mollie_provider(self):
        MollieSettings.objects.all().delete()
        PaymentProvider.objects.all().delete()
        with self.assertRaisesMessage(CommandError, "No Mollie payment provider"):
            self.run_command()

    def test_requires_api_key(self):
        MollieSettings.objects.update(test_api_key="")
        with self.assertRaisesMessage(CommandError, "no API key"):
            self.run_command()

    def make_second_provider(self, **flags):
        provider = PaymentProvider.objects.create(
            name="Mollie live",
            type="mollie",
            credit_to_account=Account.get_bank_account()[0],
            **flags,
        )
        MollieSettings.objects.create(
            payment_provider=provider, api_key="live_456", live_mode=True
        )
        return provider

    def test_multiple_settings_is_ambiguous(self):
        self.make_second_provider()
        with self.assertRaisesMessage(CommandError, "Pass --provider"):
            self.run_command()

    def test_multiple_settings_prefers_enabled_default_provider(self):
        second = self.make_second_provider(default=True, enabled=True)
        stdout, _ = self.run_command()
        self.assertIn(f"Using Mollie provider 'Mollie live' (id {second.pk}, live mode)", stdout)

    def test_provider_flag_selects_settings(self):
        self.make_second_provider(default=True, enabled=True)
        stdout, _ = self.run_command("--provider", str(self.provider.pk))
        self.assertIn(f"Using Mollie provider 'Mollie' (id {self.provider.pk}, test mode)", stdout)

    def test_provider_flag_rejects_provider_without_settings(self):
        with self.assertRaisesMessage(CommandError, "has no Mollie settings"):
            self.run_command("--provider", "999999")

    def test_rate_limit_is_retried_with_backoff(self):
        rate_limited = ResponseError({"detail": "Too many requests", "status": 429})
        piet = self.client.customers.get("cst_piet")
        piet.subscriptions.delete.side_effect = [rate_limited, rate_limited, MagicMock()]
        with patch(
            "symfexit.root.management.commands.cancel_mijnrood_subscriptions.time.sleep"
        ) as sleep:
            stdout, _ = self.run_command()
        self.assertEqual(piet.subscriptions.delete.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])
        self.assertIn("Rate limited by Mollie, retrying in 2s", stdout)
        self.assertIn("cancelled: 1", stdout)

    def test_persistent_rate_limit_becomes_failure(self):
        rate_limited = ResponseError({"detail": "Too many requests", "status": 429})
        piet = self.client.customers.get("cst_piet")
        piet.subscriptions.delete.side_effect = rate_limited
        with (
            patch(
                "symfexit.root.management.commands.cancel_mijnrood_subscriptions.time.sleep"
            ) as sleep,
            self.assertRaisesMessage(CommandError, "could not be cancelled"),
        ):
            self.run_command()
        self.assertEqual(piet.subscriptions.delete.call_count, 6)  # 1 + 5 retries
        self.assertEqual(sleep.call_count, 5)

    def test_other_api_errors_are_not_retried(self):
        server_error = ResponseError({"detail": "Internal server error", "status": 500})
        piet = self.client.customers.get("cst_piet")
        piet.subscriptions.delete.side_effect = server_error
        with (
            patch(
                "symfexit.root.management.commands.cancel_mijnrood_subscriptions.time.sleep"
            ) as sleep,
            self.assertRaisesMessage(CommandError, "1 subscriptions could not be cancelled"),
        ):
            self.run_command()
        self.assertEqual(piet.subscriptions.delete.call_count, 1)
        sleep.assert_not_called()

    def test_warns_when_nothing_found_at_mollie(self):
        # only anna remains, whose customer does not exist at Mollie
        self.write_csv(
            "admin_member",
            [
                {
                    "id": "11", "first_name": "Anna", "last_name": "Berg",
                    "mollie_customer_id": "cst_anna", "mollie_subscription_id": "sub_gone",
                },
            ],
        )
        self.write_csv("admin_support_member", [])
        _, stderr = self.run_command()
        self.assertIn("different Mollie account", stderr)
