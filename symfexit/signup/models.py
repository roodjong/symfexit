from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from hashids import Hashids

from symfexit.payments.models import Order

hashids = Hashids(salt=settings.SECRET_KEY, min_length=8)

User = get_user_model()


class DuplicateEmailError(Exception):
    pass


class MembershipApplication(models.Model):
    class Status(models.TextChoices):
        CREATED = ("created", _("Created"))
        ACCEPTED = ("accepted", _("Accepted"))
        REJECTED = ("rejected", _("Rejected"))

    id = models.AutoField(primary_key=True)
    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email address"))
    phone_number = models.CharField(_("phone number"), max_length=100)
    birth_date = models.DateField(_("date of birth"))
    address = models.CharField(_("address"), max_length=100)
    city = models.CharField(_("city"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=100)

    preferred_group = models.ForeignKey(
        "members.LocalGroup",
        on_delete=models.CASCADE,
        verbose_name=_("preferred group"),
    )
    payment_amount = models.IntegerField(_("payment amount in cents"))  # in cents

    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.CREATED
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("user"))

    _order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("subscription order"),
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("membership application")
        verbose_name_plural = _("membership applications")

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def get_absolute_url(self):
        return reverse("signup:payment", kwargs={"application_id": self.eid})

    @property
    def eid(self):
        return hashids.encode(self.id)

    eid.fget.short_description = _("external identifier")

    @classmethod
    def get_or_404(cls, eid):
        id = hashids.decode(eid)[0]
        return get_object_or_404(MembershipApplication, id=id)

    def create_user(self):
        try:
            user = User.objects.create_user(
                email=self.email,
                first_name=self.first_name,
                last_name=self.last_name,
                phone_number=self.phone_number,
                address=self.address,
                city=self.city,
                postal_code=self.postal_code,
            )
        except IntegrityError as e:
            if "members_user_unique_email_key" in e.args[0]:
                raise DuplicateEmailError from e
            else:
                raise e
        self.user = user
        if self.preferred_group:
            user.groups.add(self.preferred_group)
        self._subscription.user = user
        self._subscription.save()
        self.save()
        return user
