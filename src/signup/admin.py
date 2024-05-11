from typing import Any

from django import forms
from django.contrib import admin, messages
from django.http.request import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from signup.models import (ApplicationPayment, DuplicateEmailError,
                           MembershipApplication)


class ApplicationPaymentForm(forms.ModelForm):
    class Meta:
        help_texts = {
            'payment_url': 'Auto-generated payment URL. You can send this to the user so they can complete their payment.',
        }

        model = ApplicationPayment
        exclude = ()

@admin.register(ApplicationPayment)
class ApplicationPaymentAdmin(admin.ModelAdmin):
    form = ApplicationPaymentForm

    list_display = ("created_at", "price", "description", "payment_status")
    readonly_fields = ("created_at", "done_at", "payment_url")

    def get_form(self, request, *args, **kwargs):
        self.request = request
        return super().get_form(request, *args, **kwargs)

    def payment_url(self, obj: ApplicationPayment):
        url = obj.payment_url
        if url is None:
            raise ValueError("Payment URL is not set")
        absolute_url = self.request.build_absolute_uri(url)
        html = format_html('<a href="{}">{}</a>', absolute_url, url)
        return mark_safe(html)

    # don't show the add button
    def has_add_permission(self, request):
        return False
    # don't show the delete button
    def has_delete_permission(self, request, obj=None):
        return False
    # don't show the change button
    def has_change_permission(self, request, obj=None):
        return False

@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "status", "created_at")
    fields = (
        "created_at",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "birth_date",
        "address",
        "city",
        "postal_code",
        "preferred_group",
        "payment_amount",
        "_order",
        "_subscription",
        "status",
        "user",
    )
    readonly_fields = ("created_at", "payment_amount", "_order", "_subscription", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return obj.status == MembershipApplication.Status.CREATED

    def save_model(self, request, obj: MembershipApplication, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        if obj.status == MembershipApplication.Status.ACCEPTED:
            try:
                obj.user = obj.create_user()
            except DuplicateEmailError:
                messages.set_level(request, messages.ERROR)
                messages.error(request, "User with this email already exists. You can manually change the email address if you know this is really a new member.")
                return
        return super().save_model(request, obj, form, change)
