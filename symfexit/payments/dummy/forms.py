from django import forms

from symfexit.payments.models import Payment


class FakePayForm(forms.Form):
    payment_status = forms.ChoiceField(choices=Payment.Status.choices)
