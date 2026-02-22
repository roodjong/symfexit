from typing import Any

from django import forms
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import LocalGroup, User
from symfexit.membership.models import MembershipTier, MembershipType

CUSTOM_TIER_VALUE = "custom"


class NameWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.TextInput(attrs={"size": 8, "placeholder": _("First name")}),
            forms.TextInput(attrs={"size": 8, "placeholder": _("Last name")}),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        print(value)
        if value:
            return value
        return [None, None]


class NameField(forms.Field):
    widget = NameWidget()


class UserForm(forms.ModelForm):
    required_css_class = "required"
    member_identifier = forms.CharField(label=_("Member number"), disabled=True)
    name = NameField(label=_("Name"))
    email = forms.EmailField(label=_("Email"))
    phone_number = forms.CharField(label=_("Phone number"))
    address = forms.CharField(label=_("Address"))
    city = forms.CharField(label=_("City"))
    postal_code = forms.CharField(label=_("Postal code"))
    local_group = forms.ModelChoiceField(
        LocalGroup.objects.filter(selectable=True), label=_("Local group"), required=False
    )
    extra_information = forms.CharField(
        label=_("Extra information"), widget=forms.Textarea(attrs={"rows": 5}), required=False
    )

    class Meta:
        model = User
        fields = (
            "member_identifier",
            "name",
            "email",
            "phone_number",
            "address",
            "city",
            "postal_code",
            "local_group",
            "extra_information",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, label_suffix="", **kwargs)
        self.fields["name"].initial = (
            self.instance.first_name,
            self.instance.last_name,
        )

        self.fields["local_group"].initial = LocalGroup.objects.filter(user=self.instance).first()

    def save(self, commit=True):
        self.instance.first_name, self.instance.last_name = self.cleaned_data["name"]
        self.instance.groups.remove(*LocalGroup.objects.filter(user=self.instance))
        if self.cleaned_data["local_group"] is not None:
            self.instance.groups.add(self.cleaned_data["local_group"])
        return super().save(commit)


class PasswordChangeForm(forms.Form):
    required_css_class = "required"
    old_password = forms.CharField(
        label=_("Old password"),
        widget=forms.PasswordInput(),
    )
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(),
    )
    new_password2 = forms.CharField(
        label=_("New password (again)"),
        widget=forms.PasswordInput(),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data["old_password"]
        if not self.user.check_password(old_password):
            raise forms.ValidationError(_("Old password is incorrect"))
        return old_password

    def clean_new_password2(self):
        new_password1 = self.cleaned_data.get("new_password1")
        new_password2 = self.cleaned_data.get("new_password2")
        if new_password1 and new_password2 and new_password1 != new_password2:
            raise forms.ValidationError(_("The passwords do not match"))
        return new_password2

    def save(self, commit=True):
        self.user.set_password(self.cleaned_data["new_password1"])
        if commit:
            self.user.save()
        return self.user


class MembershipSelectionForm(forms.Form):
    required_css_class = "required"

    membership_type = forms.ModelChoiceField(
        queryset=MembershipType.objects.filter(enabled=True),
        widget=forms.HiddenInput,
        required=True,
    )

    payment_tier = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=[],
        label=_("Select your membership tier:"),
    )

    pay_more = forms.DecimalField(
        label=_("I want to pay more, namely:"),
        required=False,
        max_digits=6,
        decimal_places=2,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        membership_types = MembershipType.objects.filter(enabled=True).prefetch_related(
            Prefetch(
                "tiers",
                queryset=MembershipTier.objects.filter(enabled=True).select_related("product"),
            )
        )
        self._membership_types = list(membership_types)

        if len(self._membership_types) == 1:
            single_type = self._membership_types[0]
            self.fields["membership_type"].initial = single_type.pk
            self.fields["membership_type"].widget = forms.HiddenInput()
        else:
            self.fields["membership_type"].widget = forms.Select(
                choices=[(mt.pk, mt.name) for mt in self._membership_types]
            )
            if self._membership_types:
                self.fields["membership_type"].initial = self._membership_types[0].pk

        if self._membership_types:
            self._build_tier_choices(self._membership_types[0])

    def _build_tier_choices(self, membership_type):
        choices = []
        first_tier_value = None
        for tier in membership_type.tiers.all():
            value = str(tier.pk)
            if first_tier_value is None:
                first_tier_value = value
            choices.append((value, f"{tier.name} (\u20ac{tier.price_euros():.2f})"))
        if membership_type.allow_custom_amount:
            choices.append((CUSTOM_TIER_VALUE, _("I want to pay more, namely:")))
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
                self.add_error(
                    "payment_tier", _("This membership type does not allow a custom amount.")
                )
                return
            if not pay_more:
                self.add_error("pay_more", _("Please enter an amount."))
                return
            minimum_euros = membership_type.custom_amount_product.price_euros
            if pay_more < minimum_euros:
                self.add_error(
                    "pay_more",
                    _("Please enter an amount of at least \u20ac%(amount).2f.")
                    % {"amount": minimum_euros},
                )
        elif payment_tier:
            try:
                tier = MembershipTier.objects.get(pk=int(payment_tier))
            except (MembershipTier.DoesNotExist, ValueError):
                self.add_error("payment_tier", _("Invalid choice."))
                return
            if tier.membership_type_id != membership_type.pk:
                self.add_error(
                    "payment_tier", _("This tier does not belong to the selected membership type.")
                )

    def save(self, user):
        payment_tier_value = self.cleaned_data["payment_tier"]
        membership_type = self.cleaned_data["membership_type"]

        if payment_tier_value == CUSTOM_TIER_VALUE:
            membership_tier = None
        else:
            membership_tier = MembershipTier.objects.get(pk=int(payment_tier_value))

        user.membership_type = membership_type
        user.membership_tier = membership_tier
        user.save()
        return user
