from typing import Any

from django import forms
from django.utils import timezone

from symfexit.members.models import LocalGroup
from symfexit.signup.models import MembershipApplication


def with_classes(field, classes):
    field.extra_css_classes = classes
    return field


def two_wide(field):
    return with_classes(field, ["col-span-2"])


def wrap_css_classes(field, css_classes):
    classes = field.css_classes()
    if not classes:
        return " ".join(css_classes)
    return f"{classes} {' '.join(css_classes)}"


def birthday_years():
    return range(timezone.now().year - 40, timezone.now().year - 5)


class SignupForm(forms.Form):
    template_name_div = "signup/forms/div.html"
    required_css_class = "required"

    first_name = forms.CharField(label="Voornaam", max_length=100)
    last_name = forms.CharField(label="Achternaam", max_length=100)
    email = two_wide(forms.EmailField(label="E-mailadres"))
    phone_number = two_wide(forms.CharField(label="Telefoonnummer", max_length=100))
    birth_date = two_wide(
        forms.DateField(
            label="Geboortedatum", widget=forms.SelectDateWidget(years=birthday_years())
        )
    )
    address = two_wide(forms.CharField(label="Adres", max_length=100))
    city = two_wide(forms.CharField(label="Plaats", max_length=100))
    postal_code = two_wide(forms.CharField(label="Postcode", max_length=100))

    preferred_group = two_wide(
        forms.ModelChoiceField(
            label="Bij welke groep wil je je aansluiten",
            queryset=LocalGroup.objects.all(),
        )
    )

    TIERS_CHOICES = [
        (
            "750",
            "Ik verdien tot en met €2000 (ik betaal €7,50 contributie per kwartaal)",
        ),
        (
            "1500",
            "Ik verdien tussen €2000-€3499 (ik betaal €15,00 contributie per kwartaal)",
        ),
        (
            "2250",
            "Ik verdien €3500 of daarboven (ik betaal €22,50 contributie per kwartaal)",
        ),
        ("higher", "Ik wil meer betalen, namelijk:"),
    ]
    payment_tier = with_classes(
        forms.ChoiceField(
            widget=forms.RadioSelect,
            choices=TIERS_CHOICES,
            label="Selecteer wat er voor jou van toepassing is:",
        ),
        ["col-span-2", "payment-tier"],
    )
    pay_more = with_classes(
        forms.DecimalField(
            label="Ik wil meer betalen, namelijk:",
            required=False,
            max_digits=6,
            decimal_places=2,
        ),
        ["col-span-2", "pay-more"],
    )
    privacy_check = with_classes(
        forms.BooleanField(
            label="Ik heb het privacybeleid gelezen en ik ga daarmee akkoord.",
            required=True,
        ),
        ["checkmark"],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if hasattr(field, "extra_css_classes"):
                boundfield = self[name]
                boundfield.css_classes = wrap_css_classes(boundfield, field.extra_css_classes)
        initial_birth_date = timezone.now()
        initial_birth_date = initial_birth_date.replace(
            day=1, month=1, year=initial_birth_date.year - 18
        )
        self.fields["birth_date"].initial = initial_birth_date
        self.fields["payment_tier"].initial = "750"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        payment_tier = cleaned_data.get("payment_tier")
        pay_more = cleaned_data.get("pay_more")
        if payment_tier == "higher" and not pay_more:
            self.add_error("pay_more", "Vul een bedrag in")
        elif payment_tier != "higher" and pay_more:
            self.add_error("payment_tier", "Ongeldig")
        elif payment_tier == "higher" and pay_more <= 22.5:
            self.add_error("pay_more", "Vul een bedrag van meer dan €22,50 in")

    def payment_amount(self):
        payment_tier = self.cleaned_data["payment_tier"]
        pay_more = self.cleaned_data["pay_more"]
        if payment_tier == "higher":
            return int(pay_more * 100)
        return int(payment_tier)

    def save(self):
        return MembershipApplication.objects.create(
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            email=self.cleaned_data["email"],
            phone_number=self.cleaned_data["phone_number"],
            birth_date=self.cleaned_data["birth_date"],
            address=self.cleaned_data["address"],
            city=self.cleaned_data["city"],
            postal_code=self.cleaned_data["postal_code"],
            preferred_group=self.cleaned_data["preferred_group"],
            payment_amount=self.payment_amount(),
        )
