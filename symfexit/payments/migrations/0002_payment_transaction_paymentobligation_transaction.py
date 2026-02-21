import django.db.models.deletion
import symfexit.payments.models
from django.db import migrations, models


def backfill_transactions(apps, schema_editor):
    """Create transactions for any existing PaymentObligation/Payment rows."""
    Transaction = apps.get_model("payments", "Transaction")
    Account = apps.get_model("payments", "Account")
    PaymentObligation = apps.get_model("payments", "PaymentObligation")
    Payment = apps.get_model("payments", "Payment")

    ACCOUNT_ACCOUNTS_RECEIVABLE = 13011
    ACCOUNT_REVENUE = 82811
    ACCOUNT_BANK = 10201

    def get_or_create_account(code, name, description, credit_balance):
        account, _ = Account.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "credit_balance": credit_balance,
            },
        )
        return account

    for obligation in PaymentObligation.objects.filter(transaction__isnull=True):
        ar_account = get_or_create_account(
            ACCOUNT_ACCOUNTS_RECEIVABLE, "Accounts Receivable", "Accounts receivable", False
        )
        revenue_account = get_or_create_account(
            ACCOUNT_REVENUE, "Revenue", "Membership revenue", True
        )
        transaction = Transaction.objects.create(
            credit_account=revenue_account,
            debit_account=ar_account,
            amount_cents=int(obligation.order.product_price_euros * 100),
        )
        obligation.transaction = transaction
        obligation.save(update_fields=["transaction"])

    for payment in Payment.objects.filter(transaction__isnull=True):
        ar_account = get_or_create_account(
            ACCOUNT_ACCOUNTS_RECEIVABLE, "Accounts Receivable", "Accounts receivable", False
        )
        bank_account = get_or_create_account(
            ACCOUNT_BANK, "Bank", "Bank account (rekening-courant)", False
        )
        transaction = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=bank_account,
            amount_cents=int(payment.order.product_price_euros * 100),
        )
        payment.transaction = transaction
        payment.save(update_fields=["transaction"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        # Step 1: Add nullable transaction fields
        migrations.AddField(
            model_name="paymentobligation",
            name="transaction",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="payments.transaction",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="transaction",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="payments.transaction",
            ),
        ),
        # Step 2: Backfill existing rows
        migrations.RunPython(backfill_transactions, migrations.RunPython.noop),
        # Step 3: Make non-nullable
        migrations.AlterField(
            model_name="paymentobligation",
            name="transaction",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                to="payments.transaction",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="transaction",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                to="payments.transaction",
            ),
        ),
    ]
