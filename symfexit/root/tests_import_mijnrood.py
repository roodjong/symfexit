"""End-to-end tests for the import_mijnrood management command.

Builds a synthetic mijnrood ``app:export-everything`` directory (per the export
contract) and imports it into a test tenant.
"""

import csv
import tempfile
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
from argon2 import PasswordHasher as Argon2Hasher
from django.core.management import CommandError, call_command
from django_tenants.test.cases import FastTenantTestCase

from symfexit.documents.models import Directory, File
from symfexit.events.models import Event
from symfexit.members.models import LocalGroup, User
from symfexit.membership.models import MembershipType
from symfexit.payments.models import Account, Order, Payment, PaymentObligation
from symfexit.payments.mollie.models import MollieCustomer, MolliePayment
from symfexit.signup.models import MembershipApplication

AMSTERDAM = ZoneInfo("Europe/Amsterdam")

HEADERS = {
    "admin_membershipstatus": ["id", "name", "allowed_access"],
    "admin_division": [
        "id",
        "name",
        "phone",
        "city",
        "address",
        "post_code",
        "facebook",
        "instagram",
        "twitter",
        "email_id",
        "can_be_selected_on_application",
    ],
    "division_member": ["division_id", "member_id"],
    "admin_member": [
        "id",
        "division_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "iban",
        "address",
        "city",
        "post_code",
        "registration_time",
        "mollie_subscription_id",
        "contribution_period",
        "contribution_per_period_in_cents",
        "roles",
        "password_hash",
        "new_password_token_generated_time",
        "new_password_token",
        "country",
        "date_of_birth",
        "accept_use_personal_information",
        "mollie_customer_id",
        "create_subscription_after_payment",
        "current_membership_status_id",
        "comments",
        "middle_name",
    ],
    "admin_support_member": [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "iban",
        "address",
        "city",
        "post_code",
        "country",
        "date_of_birth",
        "registration_time",
        "mollie_customer_id",
        "mollie_subscription_id",
        "contribution_period",
        "contribution_per_period_in_cents",
        "original_id",
        "original_registration_time",
    ],
    "admin_support_membership_application": [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "iban",
        "address",
        "city",
        "post_code",
        "country",
        "date_of_birth",
        "registration_time",
        "mollie_customer_id",
        "mollie_subscription_id",
        "contribution_period",
        "contribution_per_period_in_cents",
    ],
    "admin_contribution_payment": [
        "id",
        "member_id",
        "amount_in_cents",
        "payment_time",
        "status",
        "mollie_payment_id",
        "period_year",
        "period_month_start",
        "period_month_end",
    ],
    "admin_membership_application": [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "iban",
        "address",
        "city",
        "post_code",
        "country",
        "date_of_birth",
        "registration_time",
        "contribution_period",
        "contribution_per_period_in_cents",
        "preferred_division_id",
        "mollie_customer_id",
        "paid",
        "middle_name",
        "has_sent_initial_email",
    ],
    "admin_member_revision": [
        "id",
        "member_id",
        "own",
        "revision_time",
        "first_name",
        "last_name",
        "email",
        "phone",
        "iban",
        "address",
        "city",
        "post_code",
        "country",
        "date_of_birth",
        "current_membership_status_id",
    ],
    "admin_document_folder": ["id", "parent_id", "member_created_id", "name"],
    "admin_document": [
        "id",
        "folder_id",
        "member_uploaded_id",
        "name",
        "size_in_bytes",
        "upload_file_name",
        "date_uploaded",
        "api_download_url",
    ],
    "admin_email_domain": ["id", "domain"],
    "admin_email": ["id", "user", "domain_id", "manager_id"],
    "admin_event": ["id", "division_id", "name", "description", "time_start", "time_end"],
}


class ImportMijnroodTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.export_dir = Path(tmp.name) / "export"
        self.export_dir.mkdir()
        self.cache_dir = Path(tmp.name) / "files"
        self.cache_dir.mkdir()
        self.source_dir = Path(tmp.name) / "var-documents"
        self.source_dir.mkdir()
        self.enterContext(self.settings(MEDIA_ROOT=str(Path(tmp.name) / "media")))

        self.bcrypt_password = "geheim123"
        bcrypt_hash = bcrypt.hashpw(self.bcrypt_password.encode(), bcrypt.gensalt(rounds=4))
        # Symfony/PHP emits the $2y$ marker for bcrypt
        self.bcrypt_hash = bcrypt_hash.decode().replace("$2b$", "$2y$", 1)
        self.argon2_password = "wachtwoord"
        self.argon2_hash = Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1).hash(
            self.argon2_password
        )

        self.write_export()
        self.populate_documents()
        self.stdout = StringIO()
        call_command(
            "import_mijnrood",
            str(self.export_dir),
            "--documents-cache",
            str(self.cache_dir),
            "--skip-duplicate-emails",
            # lowercase on purpose: names match case-insensitively
            "--cadre-status",
            "kaderlid",
            "--inactive-status",
            "opgezegd",
            *self.import_args(),
            stdout=self.stdout,
        )

    def populate_documents(self):
        """Pre-fill the download cache so no HTTP requests are made."""
        for doc_id, _, _, content, _ in self.document_fixtures:
            (self.cache_dir / doc_id).write_bytes(content)

    def import_args(self):
        # A subset of the rood instance's contribution.tiers config; amounts
        # are per quarter in cents.
        return [
            "--contribution-tier", "750:Minimum",
            "--contribution-tier", "1500:Basis",
            "--contribution-tier", "10000:Heel hoog",
        ]  # fmt: skip

    def write_csv(self, table, rows):
        with (self.export_dir / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS[table], restval="")
            writer.writeheader()
            writer.writerows(rows)

    def write_export(self):
        self.write_csv(
            "admin_membershipstatus",
            [
                {"id": "1", "name": "Actief", "allowed_access": "1"},
                {"id": "2", "name": "Opgezegd", "allowed_access": "0"},
                {"id": "3", "name": "Kaderlid", "allowed_access": "1"},
            ],
        )
        self.write_csv(
            "admin_division",
            [
                {"id": "1", "name": "Amsterdam", "can_be_selected_on_application": "1"},
                {"id": "2", "name": "Utrecht", "can_be_selected_on_application": "0"},
            ],
        )
        self.write_csv("division_member", [{"division_id": "1", "member_id": "10"}])
        self.write_csv(
            "admin_member",
            [
                {
                    "id": "10",
                    "division_id": "1",
                    "first_name": "Piet",
                    "last_name": "Jansen",
                    "email": "piet@example.org",
                    "phone": "0612345678",
                    "address": "Straatweg 1",
                    "city": "Amsterdam",
                    "post_code": "1011AB",
                    "registration_time": "2020-01-15",
                    "mollie_subscription_id": "sub_123",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "750",
                    "roles": '["ROLE_ADMIN"]',
                    "password_hash": self.bcrypt_hash,
                    "country": "NL",
                    "accept_use_personal_information": "1",
                    "mollie_customer_id": "cst_piet",
                    "current_membership_status_id": "1",
                },
                {
                    "id": "11",
                    "division_id": "2",
                    "first_name": "Anna",
                    "last_name": "Berg",
                    "middle_name": "van der",
                    "email": "anna@example.org",
                    "phone": "0687654321",
                    "address": "Domplein 2",
                    "city": "Utrecht",
                    "post_code": "3512JC",
                    "registration_time": "2021-06-01",
                    "contribution_period": "1",
                    "contribution_per_period_in_cents": "2250",
                    "roles": "[]",
                    "password_hash": self.argon2_hash,
                    "country": "NL",
                    "accept_use_personal_information": "0",
                    "current_membership_status_id": "2",
                    "comments": "Betaalt per kwartaal",
                },
                {
                    "id": "12",
                    "first_name": "Kees",
                    "last_name": "Vries",
                    "email": "kees@example.org",
                    "phone": "0611122233",
                    "address": "Lange straat 5, bis",
                    "city": "Den Haag",
                    "post_code": "2511CS",
                    "registration_time": "2019-11-20",
                    "contribution_period": "2",
                    "contribution_per_period_in_cents": "9000",
                    "roles": "[]",
                    "country": "NL",
                    "accept_use_personal_information": "1",
                    "current_membership_status_id": "3",
                },
                {
                    "id": "13",
                    "first_name": "Piet",
                    "last_name": "Dubbel",
                    "email": "piet@example.org",
                    "phone": "0600000000",
                    "city": "Amsterdam",
                    "post_code": "1011AB",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "750",
                    "roles": "[]",
                    "country": "NL",
                    "accept_use_personal_information": "1",
                },
            ],
        )
        self.write_csv(
            "admin_support_member",
            [
                {
                    "id": "1",
                    "first_name": "Sofie",
                    "last_name": "Bakker",
                    "email": "sofie@example.org",
                    "phone": "0644455566",
                    "address": "Kerkstraat 3",
                    "city": "Nijmegen",
                    "post_code": "6511VC",
                    "country": "NL",
                    "mollie_customer_id": "cst_sofie",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "500",
                    "original_id": "999",
                    "original_registration_time": "2018-03-01",
                },
                {
                    "id": "2",
                    "first_name": "Jan",
                    "last_name": "Smit",
                    "email": "jan@example.org",
                    "phone": "0655544433",
                    "city": "Groningen",
                    "post_code": "9711LM",
                    "country": "NL",
                    "registration_time": "2023-09-10",
                    "contribution_period": "2",
                    "contribution_per_period_in_cents": "0",
                    "original_id": "0",
                },
            ],
        )
        self.write_csv(
            "admin_support_membership_application",
            [
                {
                    "id": "1",
                    "first_name": "Steun",
                    "last_name": "Aanvrager",
                    "email": "steun@example.org",
                    "phone": "0600000001",
                    "city": "Zwolle",
                    "post_code": "8011AA",
                    "country": "NL",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "500",
                }
            ],
        )
        self.write_csv(
            "admin_contribution_payment",
            [
                {
                    "id": "1",
                    "member_id": "10",
                    "amount_in_cents": "750",
                    "payment_time": "2026-01-05 10:00:00",
                    "status": "1",
                    "mollie_payment_id": "tr_1",
                    "period_year": "2026",
                    "period_month_start": "1",
                    "period_month_end": "1",
                },
                {
                    "id": "2",
                    "member_id": "10",
                    "amount_in_cents": "750",
                    "payment_time": "2026-02-05 10:00:00",
                    "status": "1",
                    "mollie_payment_id": "tr_2",
                    "period_year": "2026",
                    "period_month_start": "2",
                    "period_month_end": "2",
                },
                # second receipt for the same period -> merged onto the same obligation
                {
                    "id": "3",
                    "member_id": "10",
                    "amount_in_cents": "750",
                    "payment_time": "2026-01-20 10:00:00",
                    "status": "1",
                    "mollie_payment_id": "tr_3",
                    "period_year": "2026",
                    "period_month_start": "1",
                    "period_month_end": "1",
                },
                # pending -> skipped
                {
                    "id": "4",
                    "member_id": "10",
                    "amount_in_cents": "750",
                    "payment_time": "2026-03-05 10:00:00",
                    "status": "0",
                    "period_year": "2026",
                    "period_month_start": "3",
                    "period_month_end": "3",
                },
                {
                    "id": "5",
                    "member_id": "11",
                    "amount_in_cents": "2250",
                    "payment_time": "2026-01-10 09:00:00",
                    "status": "1",
                    "period_year": "2026",
                    "period_month_start": "1",
                    "period_month_end": "3",
                },
                {
                    "id": "6",
                    "member_id": "12",
                    "amount_in_cents": "9000",
                    "payment_time": "2026-01-02 08:00:00",
                    "status": "1",
                    "mollie_payment_id": "tr_6",
                    "period_year": "2026",
                    "period_month_start": "1",
                    "period_month_end": "12",
                },
                # payment of a member that is not in the export anymore -> skipped
                {
                    "id": "7",
                    "member_id": "404",
                    "amount_in_cents": "500",
                    "payment_time": "2026-01-01 00:00:00",
                    "status": "1",
                    "period_year": "2026",
                    "period_month_start": "1",
                    "period_month_end": "1",
                },
            ],
        )
        self.write_csv(
            "admin_membership_application",
            [
                {
                    "id": "1",
                    "first_name": "Nieuw",
                    "last_name": "Lid",
                    "email": "nieuw@example.org",
                    "phone": "0699988877",
                    "address": "Nieuwstraat 1",
                    "city": "Amsterdam",
                    "post_code": "1012AB",
                    "country": "NL",
                    "date_of_birth": "2001-02-03",
                    "registration_time": "2026-06-15",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "1500",
                    "preferred_division_id": "1",
                    "paid": "1",
                    "has_sent_initial_email": "1",
                },
                # no date of birth -> skipped
                {
                    "id": "2",
                    "first_name": "Geen",
                    "last_name": "Geboortedatum",
                    "email": "geen@example.org",
                    "phone": "0688877766",
                    "address": "Leegstraat 1",
                    "city": "Utrecht",
                    "post_code": "3513AB",
                    "country": "NL",
                    "contribution_period": "0",
                    "contribution_per_period_in_cents": "750",
                    "paid": "0",
                    "has_sent_initial_email": "0",
                },
            ],
        )
        self.write_csv(
            "admin_member_revision",
            [
                {
                    "id": "1",
                    "member_id": "10",
                    "own": "1",
                    "revision_time": "2024-01-01 10:00:00",
                    "first_name": "Piet",
                    "last_name": "Jansen",
                    "email": "piet@example.org",
                    "phone": "0612345678",
                    "city": "Amsterdam",
                    "post_code": "1011AB",
                    "country": "NL",
                }
            ],
        )
        self.write_csv(
            "admin_document_folder",
            [
                {"id": "1", "name": "Bestuur"},
                {"id": "2", "parent_id": "1", "name": "Notulen"},
                {"id": "3", "parent_id": "99", "name": "Wees"},
            ],
        )
        documents = self.document_fixtures = [
            ("1", "", "reglement.pdf", b"PDFDATA", "2021-05-01 12:00:00"),
            ("2", "2", "notulen.txt", b"hello", "2022-06-02 13:00:00"),
            ("3", "2", "notulen.txt", b"world!", "2023-07-03 14:00:00"),
        ]
        self.write_csv(
            "admin_document",
            [
                {
                    "id": doc_id,
                    "folder_id": folder_id,
                    "name": name,
                    "size_in_bytes": str(len(content)),
                    "upload_file_name": f"upload-{doc_id}.bin",
                    "date_uploaded": uploaded,
                    "api_download_url": f"https://old.example.org/api/documenten/download/{doc_id}",
                }
                for doc_id, folder_id, name, content, uploaded in documents
            ],
        )
        self.write_csv("admin_email_domain", [{"id": "1", "domain": "roodjongeren.nl"}])
        self.write_csv(
            "admin_email", [{"id": "1", "user": "amsterdam", "domain_id": "1", "manager_id": "10"}]
        )
        self.write_csv(
            "admin_event",
            [
                {
                    "id": "1",
                    "division_id": "1",
                    "name": "Zomerfeest",
                    "description": "Feest in het park",
                    "time_start": "2026-08-01 14:00:00",
                    "time_end": "2026-08-01 22:00:00",
                },
                {
                    "id": "2",
                    "name": "Congres",
                    "description": "Landelijk congres",
                    "time_start": "2026-11-14 10:00:00",
                    "time_end": "2026-11-15 17:00:00",
                },
            ],
        )

    def test_members_imported(self):
        self.assertEqual(User.objects.count(), 5)
        piet = User.objects.get(legacy_member_number=10)
        self.assertTrue(piet.is_superuser)
        self.assertTrue(piet.is_staff)
        self.assertTrue(piet.is_active)
        self.assertEqual(piet.member_type, User.MemberType.MEMBER)
        self.assertEqual(piet.membership_type.slug, "lidmaatschap")
        self.assertEqual(piet.date_joined.astimezone(AMSTERDAM).date(), date(2020, 1, 15))
        # being a division contact also puts piet in the "Contact person" permission group
        self.assertEqual([g.name for g in LocalGroup.objects.filter(user=piet)], ["Amsterdam"])
        # duplicate email row was skipped
        self.assertFalse(User.objects.filter(legacy_member_number=13).exists())

    def test_middle_name_and_status(self):
        anna = User.objects.get(legacy_member_number=11)
        self.assertEqual(anna.last_name, "van der Berg")
        self.assertFalse(anna.is_active)
        self.assertIn("Betaalt per kwartaal", anna.extra_information)
        self.assertIn("Opgezegd", anna.extra_information)
        self.assertIn("Did NOT accept", anna.extra_information)

    def test_status_mapping(self):
        kees = User.objects.get(legacy_member_number=12)
        self.assertTrue(kees.cadre)
        self.assertTrue(kees.is_active)
        self.assertIn("Kaderlid", kees.extra_information)
        piet = User.objects.get(legacy_member_number=10)
        self.assertFalse(piet.cadre)
        anna = User.objects.get(legacy_member_number=11)
        self.assertFalse(anna.cadre)
        self.assertFalse(anna.is_active)

    def test_unknown_status_name_aborts(self):
        with self.assertRaisesMessage(
            CommandError, "Unknown membership status name(s): bestaatniet"
        ):
            call_command(
                "import_mijnrood",
                str(self.export_dir),
                "--documents-cache",
                str(self.cache_dir),
                "--cadre-status",
                "Bestaatniet",
                stdout=StringIO(),
            )

    def test_passwords(self):
        piet = User.objects.get(legacy_member_number=10)
        self.assertTrue(piet.password.startswith("bcrypt$$2b$"))
        self.assertTrue(piet.check_password(self.bcrypt_password))
        anna = User.objects.get(legacy_member_number=11)
        self.assertTrue(anna.check_password(self.argon2_password))
        kees = User.objects.get(legacy_member_number=12)
        self.assertFalse(kees.has_usable_password())

    def test_support_members(self):
        sofie = User.objects.get(email="sofie@example.org")
        self.assertEqual(sofie.member_type, User.MemberType.SUPPORT_MEMBER)
        self.assertEqual(sofie.legacy_member_number, 999)
        self.assertEqual(sofie.membership_type.slug, "steunlidmaatschap")
        self.assertEqual(sofie.date_joined.astimezone(AMSTERDAM).date(), date(2018, 3, 1))
        jan = User.objects.get(email="jan@example.org")
        self.assertIsNone(jan.legacy_member_number)

    def test_groups(self):
        amsterdam = LocalGroup.objects.get(name="Amsterdam")
        utrecht = LocalGroup.objects.get(name="Utrecht")
        self.assertTrue(amsterdam.selectable)
        self.assertFalse(utrecht.selectable)
        self.assertEqual(
            list(amsterdam.contact_people.values_list("email", flat=True)),
            ["piet@example.org"],
        )

    def test_orders_and_payments(self):
        # piet, anna, kees + sofie (jan has a contribution of 0)
        self.assertEqual(Order.objects.count(), 4)
        piet = User.objects.get(legacy_member_number=10)
        order = Order.objects.get(ordered_for=piet)
        self.assertEqual(order.subscription_period_unit, "month")
        self.assertEqual(order.subscription_period, 1)
        self.assertEqual(order.product_price_euros, Decimal("7.50"))
        self.assertEqual(order.created_at.astimezone(AMSTERDAM).date(), date(2020, 1, 15))

        obligations = order.paymentobligation_set.order_by("period")
        self.assertEqual([(o.year, o.period) for o in obligations], [(2026, 0), (2026, 1)])
        # January got two receipts (tr_1 and tr_3)
        january = obligations[0]
        self.assertEqual(january.payment_set.count(), 2)
        self.assertEqual(january.outstanding_cents, -750)

        kees = User.objects.get(legacy_member_number=12)
        kees_obligation = PaymentObligation.objects.get(order__ordered_for=kees)
        self.assertEqual((kees_obligation.year, kees_obligation.period), (2026, 2026))
        self.assertEqual(
            kees_obligation.pay_before.astimezone(AMSTERDAM).date(), date(2026, 12, 31)
        )

        # 3 for piet, 1 for anna, 1 for kees; pending + unknown-member skipped
        self.assertEqual(Payment.objects.count(), 5)
        paid_at = Payment.objects.get(transaction__amount_cents=2250).paid_at
        self.assertEqual(paid_at, datetime(2026, 1, 10, 9, 0, tzinfo=AMSTERDAM))

        bank_account, _ = Account.get_bank_account()
        self.assertEqual(bank_account.balance_cents(), 750 * 3 + 2250 + 9000)

    def test_mollie_records(self):
        self.assertEqual(
            set(MollieCustomer.objects.values_list("mollie_customer_id", flat=True)),
            {"cst_piet", "cst_sofie"},
        )
        self.assertEqual(
            set(MolliePayment.objects.values_list("mollie_payment_id", flat=True)),
            {"tr_1", "tr_2", "tr_3", "tr_6"},
        )
        self.assertEqual(MolliePayment.objects.filter(status="paid").count(), 4)

    def test_membership_types(self):
        self.assertEqual(MembershipType.objects.count(), 2)
        lidmaatschap = MembershipType.objects.get(slug="lidmaatschap")
        self.assertTrue(lidmaatschap.allow_custom_amount)
        # new custom-amount members pay quarterly; the minimum is the smallest
        # fixed tier, like in the old signup form
        self.assertEqual(lidmaatschap.custom_amount_product.subscription.period, 3)
        self.assertEqual(lidmaatschap.custom_amount_product.price_euros, Decimal("7.50"))

        tiers = list(lidmaatschap.tiers.all())
        self.assertEqual(
            [(tier.position, tier.name, tier.price_euros()) for tier in tiers],
            [
                (0, "Minimum", Decimal("7.50")),
                (1, "Basis", Decimal("15.00")),
                (2, "Heel hoog", Decimal("100.00")),
            ],
        )
        for tier in tiers:
            self.assertEqual(tier.product.subscription.period_unit, "month")
            self.assertEqual(tier.product.subscription.period, 3)

        steun = MembershipType.objects.get(slug="steunlidmaatschap")
        self.assertFalse(steun.enabled)
        self.assertEqual(steun.tiers.count(), 0)

    def test_applications(self):
        self.assertEqual(MembershipApplication.objects.count(), 1)
        application = MembershipApplication.objects.get()
        self.assertEqual(application.email, "nieuw@example.org")
        self.assertEqual(application.birth_date, date(2001, 2, 3))
        self.assertEqual(application.preferred_group.name, "Amsterdam")
        self.assertEqual(application.payment_amount_euros, Decimal("15.00"))
        self.assertEqual(application.status, MembershipApplication.Status.CREATED)

    def test_documents(self):
        self.assertEqual(Directory.objects.count(), 2)
        notulen = Directory.objects.get(name="Notulen")
        self.assertEqual(notulen.parent.name, "Bestuur")

        self.assertEqual(File.objects.count(), 3)
        reglement = File.objects.get(name="reglement.pdf")
        self.assertIsNone(reglement.parent)
        self.assertEqual(reglement.content.read(), b"PDFDATA")
        self.assertEqual(reglement.content_type, "application/pdf")
        self.assertEqual(reglement.created_at, datetime(2021, 5, 1, 12, 0, tzinfo=AMSTERDAM))
        # duplicate name in the same folder was renamed
        renamed = File.objects.get(name="notulen (2).txt")
        self.assertEqual(renamed.parent, notulen)
        self.assertEqual(renamed.content.read(), b"world!")

    def test_events(self):
        self.assertEqual(Event.objects.count(), 2)
        feest = Event.objects.get(event_name="Zomerfeest")
        self.assertEqual(feest.event_organiser, "Amsterdam")
        self.assertEqual(feest.event_date, datetime(2026, 8, 1, 14, 0, tzinfo=AMSTERDAM))
        congres = Event.objects.get(event_name="Congres")
        self.assertEqual(congres.event_organiser, "")

    def test_warnings_reported(self):
        output = self.stdout.getvalue()
        self.assertIn("admin_member_revision: 1 rows not imported", output)
        self.assertIn("admin_support_membership_application: 1 rows not imported", output)
        self.assertIn("managed mailboxes", output)
        self.assertIn("duplicate email piet@example.org", output)
        self.assertIn("no date of birth", output)


class ImportMijnroodFromSourceDirTest(ImportMijnroodTest):
    """Re-runs the whole import suite with document bytes coming from a local
    copy of mijnrood's var/documents directory instead of the download cache,
    and without --contribution-tier flags."""

    def populate_documents(self):
        for doc_id, _, _, content, _ in self.document_fixtures:
            # matches the upload_file_name column written in write_export
            (self.source_dir / f"upload-{doc_id}.bin").write_bytes(content)

    def import_args(self):
        return ["--documents-source-dir", str(self.source_dir)]

    def test_membership_types(self):
        lidmaatschap = MembershipType.objects.get(slug="lidmaatschap")
        self.assertEqual(lidmaatschap.tiers.count(), 0)
        # without tiers the minimum custom amount falls back to the smallest
        # quarterly contribution seen in the export (anna's 2250)
        self.assertEqual(lidmaatschap.custom_amount_product.subscription.period, 3)
        self.assertEqual(lidmaatschap.custom_amount_product.price_euros, Decimal("22.50"))
