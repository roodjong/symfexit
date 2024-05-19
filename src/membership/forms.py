from decimal import Decimal

from django import forms


class PaymentTierInfo(forms.Form):
    pay_anything_enabled = forms.BooleanField()
    pay_anything_help_text = forms.CharField()
    pay_more_enabled = forms.BooleanField()
    pay_more_help_text = forms.CharField()

    # def clean(self):
    #     cleaned_data = super().clean()
    #     if cleaned_data["pay_anything_enabled"] and cleaned_data["pay_more_enabled"]:
    #         raise forms.ValidationError("You can't enable both pay anything and pay more at the same time.")
    #     return cleaned_data


class PaymentTier(forms.Form):
    help_text = forms.CharField(
        widget=forms.TextInput, required=True, label="Help text"
    )
    cents_per_period = forms.DecimalField(
        max_digits=6,
        decimal_places=2,
        localize=True,
        required=True,
        label="Price per period (in €)",
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.get("initial", {})
        if "cents_per_period" not in initial:
            initial["cents_per_period"] = 0
        else:
            initial["cents_per_period"] = (Decimal(initial["cents_per_period"]) / 100).quantize(Decimal(10) ** -2)
        super().__init__(*args, **kwargs)
        self.fields["cents_per_period"].widget.attrs.update({"step": "0.01"})
