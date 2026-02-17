from django import forms


class FakePayForm(forms.Form):
    PAYMENT_CHOICES = [
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]
    payment_status = forms.ChoiceField(choices=PAYMENT_CHOICES)
