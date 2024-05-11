from django import forms

from payments.models import Order


class FakePayForm(forms.Form):
    payment_status = forms.ChoiceField(choices=Order.Status.choices)
