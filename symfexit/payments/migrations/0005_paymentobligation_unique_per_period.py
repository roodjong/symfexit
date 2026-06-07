from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_account_account_code_unique_when_not_shared'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentobligation',
            name='year',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='paymentobligation',
            name='period',
            field=models.IntegerField(),
        ),
        migrations.AddConstraint(
            model_name='paymentobligation',
            constraint=models.UniqueConstraint(
                fields=('order', 'year', 'period'),
                name='paymentobligation_unique_per_period',
            ),
        ),
    ]
