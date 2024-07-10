# Generated by Django 5.0.6 on 2024-07-10 12:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("theme", "0004_alter_currentthemeversion_version"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tailwindkey",
            name="name",
            field=models.CharField(
                choices=[
                    ("primary", "Primary Color"),
                    ("secondary", "Secondary Color"),
                ],
                max_length=20,
                unique=True,
                verbose_name="name",
            ),
        ),
        migrations.AlterField(
            model_name="tailwindkey",
            name="value",
            field=models.TextField(verbose_name="value"),
        ),
    ]
