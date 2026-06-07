from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_add_email_to_billingaddress"),
    ]

    operations = [
        # Drop the original UNIQUE on Account.code so we can replace it with a
        # partial UniqueConstraint in 0004. Idempotent (IF EXISTS) so re-applies
        # after a previously-partial run don't fail.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        # PostgreSQL auto-named the inline UNIQUE in 0001's CREATE TABLE.
                        'ALTER TABLE "payments_account" '
                        'DROP CONSTRAINT IF EXISTS "payments_account_code_key";',
                        # Clean up any leftover index from earlier versions of this
                        # migration that briefly added db_index=True.
                        'DROP INDEX IF EXISTS "payments_account_code_7f7a01ae";',
                        'DROP INDEX IF EXISTS "payments_account_code_7f7a01ae_like";',
                    ],
                    reverse_sql=(
                        'ALTER TABLE "payments_account" ADD CONSTRAINT '
                        '"payments_account_code_key" UNIQUE ("code");'
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="account",
                    name="code",
                    field=models.PositiveIntegerField(),
                ),
            ],
        ),
    ]
