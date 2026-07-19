from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0002_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="member_identifier",
            new_name="legacy_member_number",
        ),
        migrations.AlterField(
            model_name="user",
            name="legacy_member_number",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="legacy member number"
            ),
        ),
    ]
