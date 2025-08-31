from django import forms
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import LocalGroup, User


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
        LocalGroup.objects.all(), label=_("Local group"), required=False
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
