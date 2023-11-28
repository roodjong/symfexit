from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from hashids import Hashids
from membership.models import Membership

from payments.models import Payable


class ApplicationPayment(Payable):
    pass


hashids = Hashids(salt=settings.SECRET_KEY, min_length=8)

User = get_user_model()

class MembershipApplication(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    id = models.AutoField(primary_key=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=100)
    birth_date = models.DateField()
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=100)

    preferred_group = models.ForeignKey("members.LocalGroup", on_delete=models.CASCADE)
    payment_amount = models.IntegerField()  # in cents

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    _payable = models.ForeignKey(
        ApplicationPayment, on_delete=models.CASCADE, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_or_404(cls, eid):
        id = hashids.decode(eid)[0]
        return get_object_or_404(MembershipApplication, id=id)

    @property
    def eid(self):
        return hashids.encode(self.id)

    @property
    def payable(self):
        payment, _created = ApplicationPayment.objects.get_or_create(
            id=self._payable_id,
            defaults={
                "price": self.payment_amount,
                "description": "Eerste contributie voor {} {}".format(
                    self.first_name, self.last_name
                ),
                "return_url": reverse("signup:return", args=[self.eid]),
            },
        )
        self._payable = payment
        self.save()
        return payment

    def new_payable(self):
        self._payable = None
        self.save()

    def create_user(self):
        user = User.objects.create_user(
            email=self.email,
            first_name=self.first_name,
            last_name=self.last_name,
            phone_number=self.phone_number,
            address=self.address,
            city=self.city,
            postal_code=self.postal_code,
        )
        if self.preferred_group:
            user.groups.add(self.preferred_group)
        if self._payable is not None and self._payable.payment_status == Payable.Status.PAID:
            # Membership.objects.create(user=user)
            pass
        return user

    def __str__(self):
        return "{} {}".format(self.first_name, self.last_name)
