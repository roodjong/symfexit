# Generated by Django 5.0 on 2024-05-18 12:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("theme", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tailwindkey",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]
