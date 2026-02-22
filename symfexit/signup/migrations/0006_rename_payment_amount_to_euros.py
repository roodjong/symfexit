from decimal import Decimal

from django.db import migrations, models


def convert_cents_to_euros(apps, schema_editor):
    MembershipApplication = apps.get_model("signup", "MembershipApplication")
    for app in MembershipApplication.objects.all():
        app.payment_amount_euros = Decimal(app.payment_amount) / 100
        app.save(update_fields=["payment_amount_euros"])


class Migration(migrations.Migration):

    dependencies = [
        ("signup", "0005_membershipapplication_membership_tier_and_more"),
    ]

    operations = [
        # Add the new decimal field (nullable temporarily)
        migrations.AddField(
            model_name="membershipapplication",
            name="payment_amount_euros",
            field=models.DecimalField(
                decimal_places=2, max_digits=8, null=True, verbose_name="payment amount"
            ),
        ),
        # Copy data from cents to euros
        migrations.RunPython(convert_cents_to_euros, migrations.RunPython.noop),
        # Remove the old field
        migrations.RemoveField(
            model_name="membershipapplication",
            name="payment_amount",
        ),
        # Make the new field non-nullable
        migrations.AlterField(
            model_name="membershipapplication",
            name="payment_amount_euros",
            field=models.DecimalField(
                decimal_places=2, max_digits=8, verbose_name="payment amount"
            ),
        ),
    ]
