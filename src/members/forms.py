from django import forms

from members.models import User


class NameWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            forms.TextInput(attrs={"size": 8, "placeholder": "Voornaam"}),
            forms.TextInput(attrs={"size": 8, "placeholder": "Achternaam"}),
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
    member_identifier = forms.CharField(label="Lidnummer", disabled=True)
    name = NameField(label="Naam")
    email = forms.EmailField(label="E-mailadres")
    phone_number = forms.CharField(label="Telefoonnummer")
    address = forms.CharField(label="Adres")
    city = forms.CharField(label="Woonplaats")
    postal_code = forms.CharField(label="Postcode")

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
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, label_suffix="", **kwargs)
        self.fields["name"].initial = (
            self.instance.first_name,
            self.instance.last_name,
        )

    def save(self, commit=True):
        self.instance.first_name, self.instance.last_name = self.cleaned_data["name"]
        return super().save(commit)

class PasswordChangeForm(forms.Form):
    required_css_class = "required"
    old_password = forms.CharField(
        label="Oud wachtwoord",
        widget=forms.PasswordInput(),
    )
    new_password1 = forms.CharField(
        label="Nieuw wachtwoord",
        widget=forms.PasswordInput(),
    )
    new_password2 = forms.CharField(
        label="Nieuw wachtwoord (nog een keer)",
        widget=forms.PasswordInput(),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data["old_password"]
        if not self.user.check_password(old_password):
            raise forms.ValidationError("Oud wachtwoord is onjuist")
        return old_password

    def clean_new_password2(self):
        new_password1 = self.cleaned_data.get("new_password1")
        new_password2 = self.cleaned_data.get("new_password2")
        if new_password1 and new_password2 and new_password1 != new_password2:
            raise forms.ValidationError("Wachtwoorden komen niet overeen")
        return new_password2

    def save(self, commit=True):
        self.user.set_password(self.cleaned_data["new_password1"])
        if commit:
            self.user.save()
        return self.user
