# Generated by Django 5.0.6 on 2024-07-10 15:04

import theme.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("theme", "0006_remove_currentthemeversion_version"),
    ]

    operations = [
        migrations.RunSQL('DELETE FROM theme_currentthemeversion'),
        migrations.AddField(
            model_name="currentthemeversion",
            name="version",
            field=models.BigIntegerField(
                default=theme.utils.get_time_millis, unique=True, verbose_name="version"
            ),
        ),
    ]
