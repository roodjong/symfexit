from django.db import models

from payments.models import Payable

# Create your models here.
class MolliePayment(models.Model):
    id = models.AutoField(primary_key=True)
    payable = models.ForeignKey(Payable, on_delete=models.CASCADE)
    payment_id = models.CharField(max_length=100)
    body = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=["payment_id"]),
        ]
