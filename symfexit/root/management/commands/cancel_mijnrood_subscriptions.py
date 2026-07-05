"""Cancel the recurring Mollie subscriptions referenced in a mijnrood export.

The old mijnrood administration let Mollie itself charge members on a schedule
(subscription ids ``sub_...`` in admin_member.csv / admin_support_member.csv).
Symfexit instead charges payment obligations one by one, so those subscriptions
must be cancelled at Mollie at cutover or members will be charged twice.

This command reads the same export directory as ``import_mijnrood`` and cancels
every subscription it finds through the Mollie API, using the API key of the
configured Mollie payment provider of the current tenant:

    python manage.py tenant_command cancel_mijnrood_subscriptions <export-dir> --schema=<schema>

Safe to re-run: subscriptions that are already cancelled (or no longer exist)
are reported and skipped. Use --dry-run to only report subscription statuses.
"""

import csv
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from mollie.api.error import NotFoundError, ResponseError, UnauthorizedError

from symfexit.payments.models import PaymentProvider
from symfexit.payments.mollie.models import MollieSettings

HTTP_TOO_MANY_REQUESTS = 429


class Command(BaseCommand):
    help = "Cancel the Mollie subscriptions referenced in a mijnrood export"

    # Backoff schedule for rate-limited requests; the mollie client itself only
    # retries connection errors, not API error responses like 429.
    RATE_LIMIT_DELAYS = [2, 4, 8, 16, 32]

    def add_arguments(self, parser):
        parser.add_argument("export_dir", type=Path, help="Directory containing the exported CSVs")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only look up and report the subscriptions, do not cancel anything",
        )
        parser.add_argument(
            "--provider",
            type=int,
            default=None,
            metavar="ID",
            help="Id of the PaymentProvider whose Mollie API key should be used. Only needed "
            "when multiple Mollie providers with settings exist and none is uniquely the "
            "enabled default.",
        )

    def handle(self, *args, **options):
        export_dir = options["export_dir"]
        if not export_dir.is_dir():
            raise CommandError(f"{export_dir} is not a directory")

        client = self.get_mollie_client(options["provider"])
        subscriptions = self.collect_subscriptions(export_dir)
        if not subscriptions:
            self.stdout.write("No Mollie subscriptions found in the export")
            return

        cancelled = already_inactive = not_found = 0
        failures = []
        for description, customer_id, subscription_id in subscriptions:
            try:
                customer = self.call_mollie(client.customers.get, customer_id)
                subscription = self.call_mollie(customer.subscriptions.get, subscription_id)
                if subscription.status in ("canceled", "completed"):
                    self.stdout.write(f"{description}: {subscription_id} already {subscription.status}")
                    already_inactive += 1
                    continue
                if options["dry_run"]:
                    self.stdout.write(
                        f"{description}: would cancel {subscription_id} ({subscription.status})"
                    )
                    cancelled += 1
                    continue
                self.call_mollie(customer.subscriptions.delete, subscription_id)
                self.stdout.write(f"{description}: cancelled {subscription_id}")
                cancelled += 1
            except UnauthorizedError as e:
                raise CommandError(f"Mollie rejected the API key: {e}") from e
            except NotFoundError:
                self.stdout.write(
                    f"{description}: {customer_id}/{subscription_id} not found at Mollie"
                )
                not_found += 1
            except ResponseError as e:
                failures.append(f"{description}: {subscription_id}: {e}")

        verb = "would be cancelled" if options["dry_run"] else "cancelled"
        self.stdout.write("")
        self.stdout.write(f"  {verb}: {cancelled}")
        self.stdout.write(f"  already inactive: {already_inactive}")
        self.stdout.write(f"  not found at Mollie: {not_found}")
        if not_found == len(subscriptions):
            self.stderr.write(
                self.style.WARNING(
                    "None of the customers/subscriptions exist at Mollie. This usually means "
                    "the API key belongs to a different Mollie account (or test mode is on "
                    "while the subscriptions are live) — check the Mollie settings or pass "
                    "--provider."
                )
            )
        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"  {failure}"))
            raise CommandError(f"{len(failures)} subscriptions could not be cancelled; re-run to retry")
        self.stdout.write(self.style.SUCCESS("Done"))

    def call_mollie(self, func, *args):
        """Call a Mollie API function, backing off and retrying on rate limits."""
        for delay in self.RATE_LIMIT_DELAYS:
            try:
                return func(*args)
            except ResponseError as e:
                if e.status != HTTP_TOO_MANY_REQUESTS:
                    raise
                self.stdout.write(f"Rate limited by Mollie, retrying in {delay}s...")
                time.sleep(delay)
        return func(*args)

    def get_mollie_client(self, provider_id):
        settings = self.select_mollie_settings(provider_id)
        if not (settings.api_key if settings.live_mode else settings.test_api_key):
            raise CommandError(
                "The Mollie settings have no API key for the current mode "
                f"({'live' if settings.live_mode else 'test'})"
            )
        provider = settings.payment_provider
        self.stdout.write(
            f"Using Mollie provider '{provider.name}' (id {provider.pk}, "
            f"{'live' if settings.live_mode else 'test'} mode)"
        )
        return settings.get_mollie_client()

    def select_mollie_settings(self, provider_id):
        candidates = MollieSettings.objects.select_related("payment_provider").filter(
            payment_provider__type="mollie"
        )
        if provider_id is not None:
            settings = candidates.filter(payment_provider_id=provider_id).first()
            if settings is None:
                raise CommandError(
                    f"PaymentProvider {provider_id} does not exist, is not a Mollie provider, "
                    "or has no Mollie settings"
                )
            return settings
        candidates = list(candidates)
        if not candidates:
            # There may be Mollie providers without settings (e.g. created by
            # migrations); distinguish the two situations in the error.
            if PaymentProvider.objects.filter(type="mollie").exists():
                raise CommandError("The Mollie payment provider has no Mollie settings")
            raise CommandError("No Mollie payment provider is configured for this tenant")
        if len(candidates) == 1:
            return candidates[0]
        preferred = [
            s
            for s in candidates
            if s.payment_provider.enabled and s.payment_provider.default
        ]
        if len(preferred) == 1:
            return preferred[0]
        listing = ", ".join(
            f"id {s.payment_provider.pk} ('{s.payment_provider.name}', "
            f"{'live' if s.live_mode else 'test'} mode)"
            for s in candidates
        )
        raise CommandError(
            f"Multiple Mollie providers with settings exist: {listing}. "
            "Pass --provider <id> to choose which API key to use."
        )

    def collect_subscriptions(self, export_dir):
        subscriptions = []
        for table in ("admin_member", "admin_support_member"):
            path = export_dir / f"{table}.csv"
            if not path.exists():
                raise CommandError(f"Missing export file: {path}")
            with path.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    subscription_id = row.get("mollie_subscription_id", "")
                    if not subscription_id:
                        continue
                    description = (
                        f"{table} {row['id']} ({row['first_name']} {row['last_name']})"
                    )
                    customer_id = row.get("mollie_customer_id", "")
                    if not customer_id:
                        self.stderr.write(
                            self.style.WARNING(
                                f"{description}: has subscription {subscription_id} but no "
                                "mollie_customer_id; cancel it manually in the Mollie dashboard"
                            )
                        )
                        continue
                    subscriptions.append((description, customer_id, subscription_id))
        return subscriptions
