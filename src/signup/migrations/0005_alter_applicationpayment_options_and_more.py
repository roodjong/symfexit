# Generated by Django 5.0 on 2024-05-11 15:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("signup", "0004_rename__payable_membershipapplication__order"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="applicationpayment",
            options={"verbose_name": "Application payment"},
        ),
        migrations.AlterModelOptions(
            name="membershipapplication",
            options={"verbose_name": "Membership application"},
        ),
    ]
