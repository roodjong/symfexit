from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='payments_timezone',
            field=models.CharField(default='Europe/Amsterdam', max_length=100),
        ),
    ]
