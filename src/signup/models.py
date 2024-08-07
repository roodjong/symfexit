from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from hashids import Hashids

from membership.models import Membership
from payments.models import BillingAddress, Order

hashids = Hashids(salt=settings.SECRET_KEY, min_length=8)

User = get_user_model()


class ApplicationPayment(Order):
    @property
    def payment_url(self):
        appl = MembershipApplication.objects.filter(_order=self).first()
        if appl is None:
            return None
        return appl.get_absolute_url()

    class Meta:
        verbose_name = _("application payment")
        verbose_name_plural = _("application payments")


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

    preferred_group = models.ForeignKey("members.LocalGroup", on_delete=models.CASCADE, verbose_name=_("preferred group"))
    payment_amount = models.IntegerField(_("payment amount in cents"))  # in cents

    status = models.CharField(_("status"),
        max_length=10, choices=Status.choices, default=Status.CREATED
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("user"))

    _order = models.ForeignKey(
        ApplicationPayment,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("payment order"),
    )
    _subscription = models.ForeignKey(
        Membership,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("associated subscription"),
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    @classmethod
    def get_or_404(cls, eid):
        id = hashids.decode(eid)[0]
        return get_object_or_404(MembershipApplication, id=id)

    @property
    def eid(self):
        return hashids.encode(self.id)

    eid.fget.short_description = _("external identifier")

    def get_absolute_url(self):
        return reverse("signup:payment", kwargs={"application_id": self.eid})

    def get_or_create_subscription(self):
        address = BillingAddress.objects.create(
            user=self.user,
            name=f"{self.first_name} {self.last_name}",
            address=self.address,
            city=self.city,
            postal_code=self.postal_code,
        )
        subscription = Membership.objects.create(
            user=self.user,
            active_from_to=DateTimeTZRange(lower=timezone.now()),
            period_quantity=3,  # TODO: make configurable
            period_unit=Membership.PeriodUnit.MONTH,
            price_per_period=self.payment_amount,
            address=address,
        )
        self._subscription = subscription
        self.save()
        return subscription

    def create_user(self):
        try:
            with transaction.atomic():
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
                raise DuplicateEmailError
            else:
                raise e
        self.user = user
        if self.preferred_group:
            user.groups.add(self.preferred_group)
        self._subscription.user = user
        self._subscription.save()
        self.save()
        return user

    def __str__(self):
        return "{} {}".format(self.first_name, self.last_name)

    class Meta:
        verbose_name = _("membership application")
        verbose_name_plural = _("membership applications")
