# Generated by Django 4.2.7 on 2023-11-26 16:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("signup", "0002_applicationpayment"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershipapplication",
            name="_payable",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="signup.applicationpayment",
            ),
        ),
    ]
