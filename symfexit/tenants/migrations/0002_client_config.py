from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="config",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
