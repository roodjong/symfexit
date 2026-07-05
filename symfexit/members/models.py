from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, PermissionsMixin
from django.core.mail import send_mail
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.adminsite.models import GroupFlags, WellKnownPermissionGroup


class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        email = self.normalize_email(email)
        # Lookup the real model class from the global app registry so this
        # manager method can be used in migrations. This is fine because
        # managers are by definition working on the real model.
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class MemberType(models.TextChoices):
        MEMBER = "MEMBER", _("Member")
        SUPPORT_MEMBER = "SUPPORT", _("Support member")

    # Previously the primary_key of the User in the old mijnrood project.
    # Only kept for reference to the old administration; no longer assigned
    # for new members.
    legacy_member_number = models.PositiveIntegerField(
        _("legacy member number"), unique=True, null=True, blank=True
    )
    first_name = models.TextField(_("first name"))
    last_name = models.TextField(_("last name"))
    email = models.EmailField(_("email"))
    phone_number = models.TextField(_("phone number"), blank=True)
    address = models.TextField(_("address"), blank=True)
    city = models.TextField(_("city"), blank=True)
    postal_code = models.TextField(_("postal code"), blank=True)
    cadre = models.BooleanField(
        _("cadre"), default=False, help_text=_("Designates whether the member is a cadre member.")
    )
    extra_information = models.TextField(_("Extra information"), blank=True)
    member_type = models.CharField(_("member type"), default=MemberType.MEMBER, choices=MemberType)
    membership_type = models.ForeignKey(
        "membership.MembershipType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("membership type"),
    )
    membership_tier = models.ForeignKey(
        "membership.MembershipTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("membership tier"),
    )
    credit_account = models.OneToOneField(
        "payments.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("credit account"),
    )
    language = models.CharField(
        _("preferred language"),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        blank=True,
        null=False,
        help_text=_("User's preferred language for emails"),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("is registered"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. Cancel membership below instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    date_left = models.DateTimeField(
        _("date left"),
        help_text=_("Date someone's membership was cancelled"),
        null=True,
        blank=True,
    )

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(fields=["email"], name="members_user_unique_email_key"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def get_or_create_credit_account(self):
        from django.db import transaction  # noqa: PLC0415

        from symfexit.payments.models import ACCOUNT_MEMBER_CREDIT, Account  # noqa: PLC0415

        if self.credit_account_id is not None:
            return self.credit_account
        with transaction.atomic():
            account = Account.objects.create(
                code=ACCOUNT_MEMBER_CREDIT,
                name=f"Member credit: {self.pk}",
                description=f"Credit balance for member {self.get_full_name()} ({self.email})",
                credit_balance=True,
            )
            self.credit_account = account
            self.save(update_fields=["credit_account"])
        return account

    @property
    def credit_balance_cents(self) -> int:
        if self.credit_account_id is None:
            return 0
        return self.credit_account.balance_cents()

    def set_staff_rights(self) -> bool:
        # Add/remove user to contact person permission group
        contact_person_group = WellKnownPermissionGroup.get_or_create(
            WellKnownPermissionGroup.WellKnownPermissionGroups.CONTACT_PERSON
        )
        is_contact_person = self.contact_person_for_groups.count() >= 1
        if is_contact_person:
            contact_person_group.group.user_set.add(self)
        else:
            contact_person_group.group.user_set.remove(self)

        # set user as staff, if any group requires it
        for group in self.groups.all():
            try:
                if group.flags.members_become_staff:
                    self.is_staff = True
                    break
            except GroupFlags.DoesNotExist:
                pass
        else:
            self.is_staff = self.is_superuser
        return self.is_staff

    def cancel_membership(self):
        self.is_active = False
        self.date_left = timezone.now()
        self.save()
        for order in self.order_set.filter(cancelled_at__isnull=True):
            order.cancel()

    def save(self, *args, **kwargs):
        if self.pk is None:  # this is a newly created user
            self.is_staff = self.is_superuser
        else:
            self.set_staff_rights()
        super().save(*args, **kwargs)


class LocalGroup(Group):
    class Meta:
        verbose_name = _("local group")
        verbose_name_plural = _("local groups")

    def __str__(self):
        return self.name

    contact_people = models.ManyToManyField(
        User, related_name="contact_person_for_groups", verbose_name=_("contact people"), blank=True
    )

    selectable = models.BooleanField(
        _("selectable"),
        default=True,
        help_text=_("Whether this group can be selected by new members signing up"),
    )


class WorkGroup(Group):
    class Meta:
        verbose_name = _("work group")
        verbose_name_plural = _("work groups")

    def __str__(self):
        return self.name

    workgroup_contact_people = models.ManyToManyField(
        User,
        related_name="contact_person_for_working_groups",
        verbose_name=_("contact people"),
        blank=True,
    )


# START Signals for is_staff updating


def update_user_staff_rights(users: list[User]):
    for user in users:
        user.set_staff_rights()
    User.objects.bulk_update(users, ["is_staff"])


@receiver(m2m_changed, sender=User.groups.through)
def user_groups_changed(sender, instance, action, pk_set, **kwargs):
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    # Ensure instance is a User object and not a group
    if isinstance(instance, User):
        # Call your function to update user rights
        update_user_staff_rights([instance])


@receiver(m2m_changed, sender=LocalGroup.contact_people.through)
def local_group_contact_people_changed(sender, instance, action, pk_set, **kwargs):
    if action not in ["post_add", "post_remove", "post_clear"]:
        return

    # pk_set contains the IDs of the affected users
    update_user_staff_rights(User.objects.filter(pk__in=pk_set))


# END Signals for is_staff updating
