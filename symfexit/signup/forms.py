from typing import Any

from django import forms
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import LocalGroup
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.signup.models import MembershipApplication

CUSTOM_TIER_VALUE = "custom"


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
            required=False,
            empty_label=_("None"),
            label="Bij welke groep wil je je aansluiten",
            queryset=LocalGroup.objects.filter(selectable=True),
        )
    )

    membership_type = forms.ModelChoiceField(
        queryset=MembershipType.objects.filter(enabled=True),
        widget=forms.HiddenInput,
        required=True,
    )

    payment_tier = with_classes(
        forms.ChoiceField(
            widget=forms.RadioSelect,
            choices=[],
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

    def __init__(self, *args, initialgroup: str = "", **kwargs):
        super().__init__(*args, **kwargs)

        membership_types = MembershipType.objects.filter(enabled=True).prefetch_related(
            Prefetch(
                "tiers",
                queryset=MembershipTier.objects.filter(enabled=True).select_related("product"),
            )
        )
        self._membership_types = list(membership_types)

        # If only one type, set it as initial and keep hidden
        if len(self._membership_types) == 1:
            single_type = self._membership_types[0]
            self.fields["membership_type"].initial = single_type.pk
            self.fields["membership_type"].widget = forms.HiddenInput()
        else:
            self.fields["membership_type"].widget = forms.Select(
                choices=[(mt.pk, mt.name) for mt in self._membership_types]
            )
            with_classes(self.fields["membership_type"], ["col-span-2"])
            if self._membership_types:
                self.fields["membership_type"].initial = self._membership_types[0].pk

        # Build tier choices from the first (or only) membership type
        if self._membership_types:
            self._build_tier_choices(self._membership_types[0])

        for name, field in self.fields.items():
            if hasattr(field, "extra_css_classes"):
                boundfield = self[name]
                boundfield.css_classes = wrap_css_classes(boundfield, field.extra_css_classes)

        initial_birth_date = timezone.now()
        initial_birth_date = initial_birth_date.replace(
            day=1, month=1, year=initial_birth_date.year - 18
        )
        self.fields["birth_date"].initial = initial_birth_date

        initialgroup = LocalGroup.objects.filter(selectable=True, name__iexact=initialgroup).first()
        if initialgroup:
            self.fields["preferred_group"].initial = initialgroup.id

    def _build_tier_choices(self, membership_type):
        choices = []
        first_tier_value = None
        for tier in membership_type.tiers.all():
            value = str(tier.pk)
            if first_tier_value is None:
                first_tier_value = value
            choices.append((value, f"{tier.name} (€{tier.price_euros():.2f})"))
        if membership_type.allow_custom_amount:
            choices.append((CUSTOM_TIER_VALUE, "Ik wil meer betalen, namelijk:"))
        self.fields["payment_tier"].choices = choices
        if first_tier_value is not None:
            self.fields["payment_tier"].initial = first_tier_value

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        membership_type = cleaned_data.get("membership_type")
        payment_tier = cleaned_data.get("payment_tier")
        pay_more = cleaned_data.get("pay_more")

        if not membership_type:
            return

        if payment_tier == CUSTOM_TIER_VALUE:
            if not membership_type.allow_custom_amount:
                self.add_error("payment_tier", "Dit lidmaatschapstype staat geen eigen bedrag toe.")
                return
            if not pay_more:
                self.add_error("pay_more", "Vul een bedrag in")
                return
            minimum_euros = membership_type.custom_amount_product.price_euros
            if pay_more < minimum_euros:
                self.add_error(
                    "pay_more",
                    f"Vul een bedrag van minimaal €{minimum_euros:.2f} in",
                )
        # Validate that the tier belongs to the selected membership type
        elif payment_tier:
            try:
                tier = MembershipTier.objects.get(pk=int(payment_tier))
            except (MembershipTier.DoesNotExist, ValueError):
                self.add_error("payment_tier", "Ongeldige keuze.")
                return
            if tier.membership_type_id != membership_type.pk:
                self.add_error("payment_tier", "Deze keuze hoort niet bij het gekozen type.")

    def payment_amount_euros(self):
        payment_tier = self.cleaned_data["payment_tier"]
        pay_more = self.cleaned_data.get("pay_more")
        if payment_tier == CUSTOM_TIER_VALUE:
            return pay_more
        tier = MembershipTier.objects.get(pk=int(payment_tier))
        return tier.price_euros()

    def save(self):
        payment_tier_value = self.cleaned_data["payment_tier"]
        membership_tier = None
        if payment_tier_value != CUSTOM_TIER_VALUE:
            membership_tier = MembershipTier.objects.get(pk=int(payment_tier_value))

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
            payment_amount_euros=self.payment_amount_euros(),
            membership_type=self.cleaned_data["membership_type"],
            membership_tier=membership_tier,
        )
