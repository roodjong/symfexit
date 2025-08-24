from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, PermissionsMixin
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def generate_member_number():
    largest_member_number = User.objects.all().order_by("-member_identifier").first()
    if largest_member_number is None:
        return "1"

    try:
        return str(int(largest_member_number.member_identifier) + 1)
    except ValueError as e:
        raise ValueError("Did not expect non-integers in the member_identifier field") from e


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
        extra_fields.setdefault("member_identifier", generate_member_number())
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("member_identifier", generate_member_number())

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Previously the primary_key of the User in the old mijnrood project
    member_identifier = models.TextField(_("member number"), unique=True, null=False, blank=False)
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

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. Unselect this instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("member")
        verbose_name_plural = _("members")
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


class LocalGroup(Group):
    class Meta:
        verbose_name = _("local group")
        verbose_name_plural = _("local groups")

    def __str__(self):
        return self.name

    contact_people = models.ManyToManyField(
        User, related_name="contact_person_for_groups", verbose_name=_("contact people"), blank=True
    )
