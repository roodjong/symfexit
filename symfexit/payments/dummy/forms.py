from decimal import Decimal

from django import forms


class FakePayForm(forms.Form):
    PAYMENT_CHOICES = [
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]
    payment_status = forms.ChoiceField(choices=PAYMENT_CHOICES)
    amount_euros = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount (EUR)",
        help_text="Override the amount paid. Defaults to the obligation amount.",
    )
