from django import forms

from payments.models import Payable


class FakePayForm(forms.Form):
    payment_status = forms.ChoiceField(choices=Payable.Status.choices)
