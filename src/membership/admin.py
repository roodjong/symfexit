from typing import Any
from django import forms
from django.contrib import admin
from django.http import HttpRequest

from membership.models import Membership
from payments.models import BillingAddress, Order

class OrderInlineForm(forms.ModelForm):
    model = Order

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.payment_status == Order.Status.PAID:
            for field in self.fields.values():
                field.disabled = True

class OrderInline(admin.StackedInline):
    model = Order
    extra = 0
    readonly_fields = ("created_at", "done_at", "return_url")
    autocomplete_fields = ("address",)
    form = OrderInlineForm

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    inlines = (OrderInline,)
    pass
