# Generated by Django 5.1.1 on 2024-11-24 13:48

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="localgroup",
            name="contact_people",
            field=models.ManyToManyField(
                blank=True,
                related_name="contact_person_for_groups",
                to=settings.AUTH_USER_MODEL,
                verbose_name="contact people",
            ),
        ),
    ]
