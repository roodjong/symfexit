from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, PermissionsMixin
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


def generate_member_number():
    largest_member_number = User.objects.all().order_by("-member_identifier").first()
    if largest_member_number is None:
        return "1"

    try:
        return str(int(largest_member_number.member_identifier) + 1)
    except ValueError as e:
        raise ValueError(
            "Did not expect non-integers in the member_identifier field"
        ) from e


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

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    # Previously the primary_key of the User in the old mijnrood project
    member_identifier = models.TextField("Lidnummer", unique=True)
    first_name = models.TextField("Voornaam")
    last_name = models.TextField("Achternaam")
    email = models.EmailField()
    phone_number = models.TextField("Telefoonnummer")
    address = models.TextField("Adres")
    city = models.TextField("Plaats")
    postal_code = models.TextField("Postcode")

    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can log into this admin site.",
    )
    is_active = models.BooleanField(
        "active",
        default=True,
        help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.",
    )
    date_joined = models.DateTimeField("date joined", default=timezone.now)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["member_identifier", "first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "member"
        constraints = [
            models.UniqueConstraint(
                fields=["email"], name="members_user_unique_email_key"
            ),
        ]

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = "%s %s" % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class LocalGroup(Group):
    contact_people = models.ManyToManyField(
        User, related_name="contact_person_for_groups"
    )
