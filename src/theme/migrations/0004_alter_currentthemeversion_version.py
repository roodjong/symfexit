# Generated by Django 5.0.6 on 2024-06-22 11:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("theme", "0003_currentthemeversion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="currentthemeversion",
            name="version",
            field=models.DateTimeField(auto_now=True),
        ),
    ]