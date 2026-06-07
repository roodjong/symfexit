from django.db import migrations


def backfill_processed_at(apps, schema_editor):
    """MolliePayments that already reached a terminal status (paid, failed,
    canceled, expired, ...) under the pre-processed_at code were processed
    via the old Payment-exists guard. Mark them as processed at creation time
    so a stale webhook re-fire doesn't trigger _record_receipt against them.

    Defensive: if the table or required columns aren't present on this schema
    (django-tenants schemas can be at different states during migration), skip
    silently — there's nothing to backfill on a non-conforming schema.
    """
    MolliePayment = apps.get_model("mollie", "MolliePayment")
    table = MolliePayment._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = current_schema()",
            [table],
        )
        columns = {row[0] for row in cursor.fetchall()}
        required = {"status", "processed_at", "created_at"}
        if not required.issubset(columns):
            return
        cursor.execute(
            f'UPDATE "{table}" SET "processed_at" = "created_at" '
            f'WHERE "processed_at" IS NULL AND "status" NOT IN (%s, %s)',
            ["open", ""],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("mollie", "0006_molliepayment_processed_at"),
    ]

    operations = [
        migrations.RunPython(backfill_processed_at, migrations.RunPython.noop),
    ]
