from django.db import models

from symfexit.payments.models import Order


# Create your models here.
class MolliePayment(models.Model):
    id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment_id = models.CharField(max_length=100)
    body = models.JSONField()

    class Meta:
        indexes = [
            models.Index(fields=["payment_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.order} - {self.payment_id}"
