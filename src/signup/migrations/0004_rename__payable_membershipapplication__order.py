# Generated by Django 4.2.7 on 2024-05-10 09:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("signup", "0003_alter_membershipapplication__payable_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="membershipapplication",
            old_name="_payable",
            new_name="_order",
        ),
    ]
