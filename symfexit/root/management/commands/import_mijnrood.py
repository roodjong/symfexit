"""Import a mijnrood export (``app:export-everything`` CSV directory) into symfexit.

The export format is documented in the mijnrood project ("Export contract:
app:export-everything"). This command consumes such a directory and creates the
corresponding symfexit records in the *current tenant schema*, so run it as:

    python manage.py tenant_command import_mijnrood <export-dir> --schema=<schema>

(or plainly with ``manage.py import_mijnrood`` in SINGLE_SITE setups).

What is imported:

- admin_membershipstatus  -> User.is_active + note in extra_information
- admin_division          -> members.LocalGroup (+ member's group membership)
- division_member         -> LocalGroup.contact_people
- admin_member            -> members.User (member_type=MEMBER)
- admin_support_member    -> members.User (member_type=SUPPORT)
- mollie_customer_id      -> payments.mollie.MollieCustomer
- contribution settings   -> membership.MembershipType + payments Product/
                             Subscription/BillingAddress/Order per user
- admin_contribution_payment (status=paid)
                          -> payments.PaymentObligation/Payment/Transaction
                             (+ MolliePayment when a Mollie id is present)
- admin_membership_application -> signup.MembershipApplication
- admin_document_folder   -> documents.Directory
- admin_document          -> documents.File (bytes fetched from the old server
                             using the EXPORT_KEY environment variable, or from
                             a local copy of mijnrood's var/documents via
                             --documents-source-dir; --documents-base-url fixes
                             exports whose URLs point at http://localhost)
- admin_event             -> events.Event

Deliberately not imported (kept only in the CSV archive): admin_member_revision
(audit trail), admin_email / admin_email_domain (managed mailboxes),
admin_support_membership_application (no support signup flow in symfexit),
Mollie subscription ids (the old Mollie subscriptions must be cancelled at
cutover; symfexit charges per obligation instead).

Old primary keys are preserved as User.legacy_member_number (for support
members only when they were converted from a full member, via original_id).
"""

import csv
import json
import mimetypes
import os
import urllib.request
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from symfexit.documents.models import Directory, File
from symfexit.events.models import Event
from symfexit.members.models import LocalGroup, User
from symfexit.membership.models import MembershipType
from symfexit.payments.models import (
    Account,
    BillingAddress,
    Order,
    Payment,
    PaymentObligation,
    PaymentProvider,
    Product,
    Subscription,
    Transaction,
)
from symfexit.payments.mollie.models import MollieCustomer, MolliePayment
from symfexit.signup.models import MembershipApplication

AMSTERDAM = ZoneInfo("Europe/Amsterdam")

# admin_member.contribution_period / admin_support_member.contribution_period
PERIOD_MONTHLY = 0
PERIOD_QUARTERLY = 1
PERIOD_ANNUALLY = 2

# admin_contribution_payment.status
PAYMENT_PENDING = 0
PAYMENT_PAID = 1
PAYMENT_FAILED = 2
PAYMENT_REFUNDED = 3


class DryRunRollback(Exception):
    pass


def parse_datetime(value):
    """Naive 'YYYY-MM-DD HH:MM:SS' in server-local (Amsterdam) time -> aware."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=AMSTERDAM)


def parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def date_to_datetime(value):
    if value is None:
        return None
    return datetime.combine(value, time(12, 0), tzinfo=AMSTERDAM)


def parse_bool(value):
    return value == "1"


def parse_int(value, default=None):
    if value in ("", None):
        return default
    return int(value)


def convert_password_hash(symfony_hash):
    """Convert a Symfony modular-crypt hash to Django's encoded format.

    The old project used the Symfony "auto" hasher: bcrypt ($2y$...) or
    argon2id ($argon2id$...). Both algorithms are in PASSWORD_HASHERS; only
    the encoding prefix differs. Returns None when the hash is unusable.
    """
    if not symfony_hash:
        return None
    if symfony_hash.startswith(("$2y$", "$2a$", "$2b$")):
        # The python bcrypt library rejects PHP's $2y$ marker, but $2y$ and
        # $2b$ are the same algorithm.
        return "bcrypt$" + "$2b$" + symfony_hash[4:]
    if symfony_hash.startswith("$argon2"):
        return "argon2" + symfony_hash
    return None


DECEMBER = 12


def last_day_of_month(year, month):
    if month == DECEMBER:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


class Command(BaseCommand):
    help = "Import a mijnrood 'export-everything' CSV directory into the current tenant"

    def add_arguments(self, parser):
        parser.add_argument("export_dir", type=Path, help="Directory containing the exported CSVs")
        parser.add_argument(
            "--documents-cache",
            type=Path,
            default=None,
            help="Directory where document files are downloaded to and read from "
            "(default: <export_dir>/files). Downloads are resumable; existing files are kept.",
        )
        parser.add_argument(
            "--skip-documents",
            action="store_true",
            help="Do not download or import document files (folders are still imported)",
        )
        parser.add_argument(
            "--documents-base-url",
            default=None,
            help="Replace the scheme and host of every api_download_url with this base URL "
            "(e.g. https://mijn.example.org). Useful when the export was made on a machine "
            "where the app URL resolved to http://localhost.",
        )
        parser.add_argument(
            "--documents-source-dir",
            type=Path,
            default=None,
            help="Read document bytes from this local copy of mijnrood's var/documents "
            "directory (matched via upload_file_name) instead of downloading them over HTTP. "
            "EXPORT_KEY is not needed in this mode.",
        )
        parser.add_argument(
            "--skip-duplicate-emails",
            action="store_true",
            help="When two exported rows share an email address, import the first and skip the "
            "rest instead of aborting",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the whole import and roll back at the end",
        )

    def handle(self, *args, **options):
        self.export_dir = options["export_dir"]
        if not self.export_dir.is_dir():
            raise CommandError(f"{self.export_dir} is not a directory")
        self.skip_duplicate_emails = options["skip_duplicate_emails"]
        self.warnings = []
        self.counts = {}

        # Old id -> new object mappings
        self.groups = {}
        self.users = {}  # admin_member.id -> User
        self.orders = {}  # User.pk -> (Order, BillingAddress)
        self.statuses = {}  # admin_membershipstatus.id -> (name, allowed_access)
        self.seen_emails = {}

        if options["skip_documents"]:
            self.documents_cache = None
        else:
            self.documents_cache = options["documents_cache"] or self.export_dir / "files"
            self.documents_base_url = options["documents_base_url"]
            self.documents_source_dir = options["documents_source_dir"]
            self.download_documents()

        try:
            with transaction.atomic():
                self.import_statuses()
                self.import_groups()
                self.setup_contribution_products()
                self.import_members()
                self.import_group_contacts()
                self.import_support_members()
                self.import_contribution_payments()
                self.import_applications()
                self.import_documents()
                self.import_events()
                self.report_skipped_tables()
                if options["dry_run"]:
                    raise DryRunRollback
        except DryRunRollback:
            self.stdout.write(self.style.WARNING("Dry run: all changes rolled back"))

        self.stdout.write("")
        for name, count in self.counts.items():
            self.stdout.write(f"  {name}: {count}")
        if self.warnings:
            self.stdout.write(self.style.WARNING(f"\n{len(self.warnings)} warnings:"))
            for warning in self.warnings:
                self.stdout.write(self.style.WARNING(f"  - {warning}"))
        self.stdout.write(self.style.SUCCESS("Import finished"))

    # -- helpers ----------------------------------------------------------

    def rows(self, table, *, required=True):
        path = self.export_dir / f"{table}.csv"
        if not path.exists():
            if required:
                raise CommandError(f"Missing export file: {path}")
            return
        with path.open(newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)

    def warn(self, message):
        self.warnings.append(message)

    def count(self, name, amount=1):
        self.counts[name] = self.counts.get(name, 0) + amount

    def claim_email(self, email, description):
        """Emails must be unique on User. Returns False when this row must be skipped."""
        key = email.strip().lower()
        if not key:
            self.warn(f"{description}: empty email address, skipped")
            return False
        if key in self.seen_emails:
            message = f"{description}: duplicate email {email} (also used by {self.seen_emails[key]})"
            if not self.skip_duplicate_emails:
                raise CommandError(
                    message + ". Clean up the export or pass --skip-duplicate-emails."
                )
            self.warn(message + ", skipped")
            return False
        self.seen_emails[key] = description
        return True

    def show_progress(self, current, total, label):
        """Single-line progress bar on a terminal, occasional lines otherwise."""
        if self.stdout.isatty():
            width = 30
            filled = round(width * current / total)
            bar = "█" * filled + "░" * (width - filled)
            label = label if len(label) <= 40 else label[:39] + "…"  # noqa: PLR2004
            self.stdout.write(f"\r{bar} {current}/{total} {label:<40}", ending="")
            self.stdout.flush()
            if current == total:
                self.stdout.write("")
        elif current % 25 == 0 or current == total:
            self.stdout.write(f"{current}/{total} documents...")

    # -- stage 0: document download ---------------------------------------

    def download_documents(self):
        rows = list(self.rows("admin_document"))
        if not rows:
            return
        self.documents_cache.mkdir(parents=True, exist_ok=True)
        missing = []
        for row in rows:
            target = self.documents_cache / row["id"]
            expected_size = parse_int(row["size_in_bytes"], default=0)
            if not (target.exists() and target.stat().st_size == expected_size):
                missing.append(row)
        if not missing:
            self.stdout.write(f"All {len(rows)} document files present in {self.documents_cache}")
            return
        if self.documents_source_dir is not None:
            failures = self.copy_documents_from_disk(missing)
        else:
            failures = self.download_documents_over_http(missing)
        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(f"  {failure}"))
            raise CommandError(
                f"{len(failures)} document fetches failed. Fix the failures and re-run "
                "(already fetched files are cached), or pass --skip-documents."
            )
        self.stdout.write(f"All {len(rows)} document files present in {self.documents_cache}")

    def copy_documents_from_disk(self, missing):
        failures = []
        for i, row in enumerate(missing, start=1):
            self.show_progress(i, len(missing), row["name"])
            source = self.documents_source_dir / row["upload_file_name"]
            if not source.is_file():
                failures.append(f"document {row['id']} ({row['name']}): {source} does not exist")
                continue
            content = source.read_bytes()
            expected_size = parse_int(row["size_in_bytes"], default=0)
            if len(content) != expected_size:
                self.warn(
                    f"admin_document {row['id']} ({row['name']}): size on disk "
                    f"({len(content)}) differs from export metadata ({expected_size})"
                )
            (self.documents_cache / row["id"]).write_bytes(content)
        return failures

    def download_documents_over_http(self, missing):
        export_key = os.environ.get("EXPORT_KEY")
        if not export_key:
            raise CommandError(
                "EXPORT_KEY environment variable is required to download document files "
                "(or pass --skip-documents / --documents-source-dir)"
            )
        failures = []
        for i, row in enumerate(missing, start=1):
            self.show_progress(i, len(missing), row["name"])
            url = row["api_download_url"]
            if not url:
                failures.append(f"document {row['id']} has no api_download_url")
                continue
            if self.documents_base_url:
                base = urlsplit(self.documents_base_url)
                original = urlsplit(url)
                url = urlunsplit(
                    (base.scheme, base.netloc, original.path, original.query, original.fragment)
                )
            request = urllib.request.Request(url, headers={"Authorization": export_key})
            try:
                with urllib.request.urlopen(request) as response:
                    (self.documents_cache / row["id"]).write_bytes(response.read())
            except OSError as e:
                failures.append(f"document {row['id']} ({row['name']}): {e}")
                continue
        return failures

    # -- stages ------------------------------------------------------------

    def import_statuses(self):
        for row in self.rows("admin_membershipstatus"):
            self.statuses[row["id"]] = (row["name"], parse_bool(row["allowed_access"]))

    def import_groups(self):
        for row in self.rows("admin_division"):
            group = LocalGroup.objects.create(
                name=row["name"],
                selectable=parse_bool(row["can_be_selected_on_application"]),
            )
            self.groups[row["id"]] = group
            self.count("local groups")
        if any(True for _ in self.rows("admin_email", required=False)):
            self.warn(
                "admin_email/admin_email_domain: managed mailboxes have no symfexit "
                "equivalent and were not imported (this includes division contact emails)"
            )

    def setup_contribution_products(self):
        """One MembershipType per member kind, with custom-amount products per period.

        The old system stored a free-form amount and a period per member, so
        everything maps to "custom amount" products; there are no fixed tiers.
        """
        bank_account, _ = Account.get_bank_account()
        self.provider = PaymentProvider.objects.filter(type="mollie").first()
        if self.provider is None:
            self.provider = PaymentProvider.objects.create(
                name="Mollie",
                type="mollie",
                credit_to_account=bank_account,
                default=not PaymentProvider.objects.filter(default=True).exists(),
            )
            self.warn(
                "Created a Mollie payment provider without API keys; configure it in the admin"
            )

        periods = {
            PERIOD_MONTHLY: ("contributie-maandelijks", "Contributie (maandelijks)", "month", 1),
            PERIOD_QUARTERLY: ("contributie-kwartaal", "Contributie (per kwartaal)", "month", 3),
            PERIOD_ANNUALLY: ("contributie-jaarlijks", "Contributie (jaarlijks)", "year", 1),
        }
        # The custom product's price acts as the minimum for "pay more"; use the
        # smallest amount actually paid in the old administration per period.
        minimums = {}
        for table in ("admin_member", "admin_support_member"):
            for row in self.rows(table):
                period = parse_int(row["contribution_period"])
                cents = parse_int(row["contribution_per_period_in_cents"], default=0)
                if cents > 0 and (period not in minimums or cents < minimums[period]):
                    minimums[period] = cents

        self.products = {}
        for period, (sku, name, unit, count) in periods.items():
            product = Product.objects.create(
                enabled=True,
                sku=sku,
                name=name,
                price_euros=Decimal(minimums.get(period, 100)) / 100,
                type="subscription",
            )
            Subscription.objects.create(product=product, period_unit=unit, period=count)
            self.products[period] = product

        self.member_type = MembershipType.objects.create(
            name="Lidmaatschap",
            slug="lidmaatschap",
            allow_custom_amount=True,
            custom_amount_product=self.products[PERIOD_MONTHLY],
        )
        self.support_type = MembershipType.objects.create(
            name="Steunlidmaatschap",
            slug="steunlidmaatschap",
            enabled=False,
            allow_custom_amount=True,
            custom_amount_product=self.products[PERIOD_MONTHLY],
        )

    def build_user(self, row, *, member_type, legacy_number, description):
        """Shared between admin_member and admin_support_member rows."""
        last_name = row["last_name"]
        # admin_support_member rows have no middle_name column
        if row.get("middle_name"):
            last_name = f"{row['middle_name']} {last_name}"

        password = convert_password_hash(row.get("password_hash"))
        if password is None:
            password = make_password(None)

        extra_lines = []
        if row.get("comments"):
            extra_lines.append(row["comments"])
        status_id = row.get("current_membership_status_id")
        is_active = True
        if status_id:
            status_name, allowed_access = self.statuses.get(status_id, (None, True))
            is_active = allowed_access
            if status_name:
                extra_lines.append(f"Membership status (mijnrood): {status_name}")
        if row.get("accept_use_personal_information") == "0":
            extra_lines.append("Did NOT accept use of personal information (mijnrood)")

        registration = parse_date(row["registration_time"])
        user = User(
            legacy_member_number=legacy_number,
            member_type=member_type,
            first_name=row["first_name"],
            last_name=last_name,
            email=row["email"],
            phone_number=row["phone"] or "",
            address=row["address"] or "",
            city=row["city"] or "",
            postal_code=row["post_code"] or "",
            extra_information="\n".join(extra_lines),
            is_active=is_active,
            date_joined=date_to_datetime(registration) or datetime.now(tz=AMSTERDAM),
            password=password,
        )
        user.save()
        self.link_mollie_customer(user, row.get("mollie_customer_id"), description)
        self.create_contribution_order(user, row, registration, description)
        if row.get("mollie_subscription_id"):
            # symfexit charges per obligation; recurring Mollie subscriptions
            # from the old system must be cancelled at Mollie at cutover.
            self.count("old Mollie subscriptions (cancel these at Mollie!)")
        return user

    def link_mollie_customer(self, user, mollie_customer_id, description):
        if not mollie_customer_id:
            return
        if MollieCustomer.objects.filter(mollie_customer_id=mollie_customer_id).exists():
            self.warn(f"{description}: mollie customer {mollie_customer_id} already linked")
            return
        MollieCustomer.objects.create(user=user, mollie_customer_id=mollie_customer_id)
        self.count("mollie customers")

    def create_contribution_order(self, user, row, registration, description):
        cents = parse_int(row["contribution_per_period_in_cents"], default=0)
        period = parse_int(row["contribution_period"])
        if cents <= 0:
            self.warn(f"{description}: contribution is 0, no order created")
            return
        product = self.products.get(period)
        if product is None:
            self.warn(f"{description}: unknown contribution_period {period}, no order created")
            return
        billing_address = BillingAddress.objects.create(
            user=user,
            name=user.get_full_name(),
            email=user.email,
            address=user.address,
            city=user.city,
            postal_code=user.postal_code,
        )
        order = Order.objects.create(
            product=product,
            product_sku=product.sku,
            product_name=product.name,
            product_price_euros=Decimal(cents) / 100,
            subscription=product.subscription,
            subscription_period_unit=product.subscription.period_unit,
            subscription_period=product.subscription.period,
            ordered_for=user,
            ordered_for_billing_address=billing_address,
            paid_using=self.provider,
        )
        # created_at is the anchor for future obligation periods; backdate it
        # to the old registration date (auto_now_add ignores values on create).
        created_at = date_to_datetime(registration)
        if created_at:
            Order.objects.filter(pk=order.pk).update(created_at=created_at)
            order.created_at = created_at
        self.orders[user.pk] = (order, billing_address)
        self.count("contribution orders")

    def import_members(self):
        for row in self.rows("admin_member"):
            description = f"admin_member {row['id']} ({row['first_name']} {row['last_name']})"
            if not self.claim_email(row["email"], description):
                self.count("skipped members")
                continue
            user = self.build_user(
                row,
                member_type=User.MemberType.MEMBER,
                legacy_number=parse_int(row["id"]),
                description=description,
            )
            user.membership_type = self.member_type
            if json_roles := row["roles"]:
                if "ROLE_ADMIN" in json.loads(json_roles):
                    user.is_superuser = True
            user.save()
            if row["division_id"]:
                user.groups.add(self.groups[row["division_id"]])
            self.users[row["id"]] = user
            self.count("members")

    def import_group_contacts(self):
        for row in self.rows("division_member"):
            group = self.groups.get(row["division_id"])
            user = self.users.get(row["member_id"])
            if group is None or user is None:
                self.warn(
                    f"division_member ({row['division_id']}, {row['member_id']}): "
                    "unknown division or member, skipped"
                )
                continue
            group.contact_people.add(user)
            self.count("group contacts")

    def import_support_members(self):
        for row in self.rows("admin_support_member"):
            description = (
                f"admin_support_member {row['id']} ({row['first_name']} {row['last_name']})"
            )
            if not self.claim_email(row["email"], description):
                self.count("skipped support members")
                continue
            original_id = parse_int(row["original_id"], default=0)
            registration_time = row["registration_time"] or row["original_registration_time"]
            user = self.build_user(
                dict(row, registration_time=registration_time),
                member_type=User.MemberType.SUPPORT_MEMBER,
                legacy_number=original_id or None,
                description=description,
            )
            user.membership_type = self.support_type
            user.save()
            self.count("support members")

    def import_contribution_payments(self):
        ar_account, _ = Account.get_accounts_receivable_account()
        revenue_account, _ = Account.get_revenue_account()
        for row in self.rows("admin_contribution_payment"):
            status = parse_int(row["status"])
            if status != PAYMENT_PAID:
                self.count("payments skipped (not status=paid)")
                continue
            user = self.users.get(row["member_id"])
            order_info = self.orders.get(user.pk) if user else None
            if order_info is None:
                self.count("payments skipped (no member/order)")
                continue
            order, billing_address = order_info
            amount_cents = parse_int(row["amount_in_cents"], default=0)
            paid_at = parse_datetime(row["payment_time"])
            year = parse_int(row["period_year"])
            month_start = parse_int(row["period_month_start"], default=1)
            month_end = parse_int(row["period_month_end"], default=12)

            if order.subscription_period_unit == "year":
                period = year
            else:
                period = month_start - 1
            pay_before = datetime.combine(
                last_day_of_month(year, month_end), time(23, 59, 59), tzinfo=AMSTERDAM
            )

            obligation = order.paymentobligation_set.filter(year=year, period=period).first()
            if obligation is None:
                obligation_tx = Transaction.objects.create(
                    credit_account=revenue_account,
                    debit_account=ar_account,
                    amount_cents=amount_cents,
                )
                obligation = PaymentObligation.objects.create(
                    order=order,
                    transaction=obligation_tx,
                    year=year,
                    period=period,
                    pay_before=pay_before,
                    amount_euros=Decimal(amount_cents) / 100,
                    ordered_for_billing_address=billing_address,
                )
                PaymentObligation.objects.filter(pk=obligation.pk).update(created_at=paid_at)
                Transaction.objects.filter(pk=obligation_tx.pk).update(created_at=paid_at)
            else:
                # Two old payments covering the same period (e.g. after a
                # period switch): book the receipt onto the same obligation.
                self.count("payments merged into an existing period")

            payment_tx = Transaction.objects.create(
                credit_account=ar_account,
                debit_account=self.provider.credit_to_account,
                amount_cents=amount_cents,
            )
            payment = Payment.objects.create(
                order=order,
                obligation=obligation,
                transaction=payment_tx,
                paid_using=self.provider,
                paid_at=paid_at,
            )
            Payment.objects.filter(pk=payment.pk).update(created_at=paid_at)
            Transaction.objects.filter(pk=payment_tx.pk).update(created_at=paid_at)

            mollie_id = row["mollie_payment_id"]
            if mollie_id and not MolliePayment.objects.filter(mollie_payment_id=mollie_id).exists():
                MolliePayment.objects.create(
                    obligation=obligation,
                    mollie_payment_id=mollie_id,
                    status="paid",
                    processed_at=paid_at,
                )
            self.count("payments")

    def import_applications(self):
        for row in self.rows("admin_membership_application"):
            description = (
                f"admin_membership_application {row['id']} "
                f"({row['first_name']} {row['last_name']})"
            )
            birth_date = parse_date(row["date_of_birth"])
            if birth_date is None:
                self.warn(f"{description}: no date of birth, skipped (re-apply in symfexit)")
                continue
            last_name = row["last_name"]
            if row["middle_name"]:
                last_name = f"{row['middle_name']} {last_name}"
            application = MembershipApplication.objects.create(
                first_name=row["first_name"],
                last_name=last_name,
                email=row["email"],
                phone_number=row["phone"],
                birth_date=birth_date,
                address=row["address"] or "",
                city=row["city"],
                postal_code=row["post_code"],
                preferred_group=self.groups.get(row["preferred_division_id"]),
                payment_amount_euros=(
                    Decimal(parse_int(row["contribution_per_period_in_cents"], default=0)) / 100
                ),
                membership_type=self.member_type,
            )
            registration = date_to_datetime(parse_date(row["registration_time"]))
            if registration:
                MembershipApplication.objects.filter(pk=application.pk).update(
                    created_at=registration
                )
            if parse_bool(row["paid"]):
                self.warn(
                    f"{description}: was already paid in mijnrood; the payment was not "
                    "carried over, accept the application without charging again"
                )
            self.count("membership applications")

    def import_documents(self):
        folders = {}
        pending = list(self.rows("admin_document_folder"))
        while pending:
            remaining = []
            for row in pending:
                parent_id = row["parent_id"]
                if parent_id and parent_id not in folders:
                    remaining.append(row)
                    continue
                folders[row["id"]] = Directory.objects.create(
                    name=row["name"],
                    parent=folders.get(parent_id),
                )
                self.count("document folders")
            if len(remaining) == len(pending):
                self.warn(
                    f"document folders with unresolvable parents skipped: "
                    f"{[row['id'] for row in remaining]}"
                )
                break
            pending = remaining

        used_names = {}
        for row in self.rows("admin_document"):
            if self.documents_cache is None:
                self.count("documents skipped (--skip-documents)")
                continue
            content = (self.documents_cache / row["id"]).read_bytes()
            parent = folders.get(row["folder_id"])
            name = row["name"]
            # (parent, name) must be unique; deduplicate exported name clashes
            suffix = 1
            while (parent, name) in used_names:
                suffix += 1
                stem, dot, extension = row["name"].rpartition(".")
                if dot:
                    name = f"{stem} ({suffix}).{extension}"
                else:
                    name = f"{row['name']} ({suffix})"
            if name != row["name"]:
                self.warn(f"admin_document {row['id']}: renamed duplicate '{row['name']}' to '{name}'")
            used_names[(parent, name)] = True
            document = File.objects.create(
                name=name,
                parent=parent,
                content=ContentFile(content, name=name),
                size=len(content),
                content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
            )
            uploaded_at = parse_datetime(row["date_uploaded"])
            if uploaded_at:
                File.objects.filter(pk=document.pk).update(created_at=uploaded_at)
            self.count("documents")

    def import_events(self):
        for row in self.rows("admin_event"):
            organiser = ""
            if row["division_id"] and row["division_id"] in self.groups:
                organiser = self.groups[row["division_id"]].name
            Event.objects.create(
                event_name=row["name"],
                event_organiser=organiser,
                event_date=parse_datetime(row["time_start"]),
                event_end=parse_datetime(row["time_end"]),
                event_desc=row["description"],
            )
            self.count("events")

    def report_skipped_tables(self):
        for table, reason in [
            ("admin_member_revision", "audit trail has no symfexit equivalent"),
            ("admin_support_membership_application", "no support signup flow in symfexit"),
        ]:
            skipped = sum(1 for _ in self.rows(table, required=False))
            if skipped:
                self.warn(f"{table}: {skipped} rows not imported ({reason})")
