from django.contrib import admin, messages
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from symfexit.emails._templates.emails.signup_accepted import SignupAcceptedEmail
from symfexit.emails._templates.render import send_email
from symfexit.signup.models import DuplicateEmailError, MembershipApplication


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "membership_type", "status", "created_at")
    change_form_template = "signup/admin/change_form.html"
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
        "membership_type",
        "membership_tier",
        "payment_amount_euros",
        "_order",
        "status",
        "user",
    )
    readonly_fields = (
        "created_at",
        "payment_amount_euros",
        "membership_type",
        "membership_tier",
        "_order",
        "user",
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:pk>/resend-accepted-email/",
                self.admin_site.admin_view(self.resend_accepted_email_view),
                name="signup_membershipapplication_resend_accepted_email",
            ),
        ]
        return custom_urls + urls

    def resend_accepted_email_view(self, request, pk):
        obj = self.get_object(request, pk)
        if obj and obj.status == MembershipApplication.Status.ACCEPTED and obj.user:
            self.send_signup_accepted_email(request, obj)
            messages.success(request, f"Accepted email resent to {obj.email}.")
        return HttpResponseRedirect(reverse("admin:signup_membershipapplication_change", args=[pk]))

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj and obj.status == MembershipApplication.Status.ACCEPTED and obj.user:
                extra_context["show_resend_button"] = True
                extra_context["resend_url"] = reverse(
                    "admin:signup_membershipapplication_resend_accepted_email",
                    args=[object_id],
                )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return obj.status == MembershipApplication.Status.CREATED

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        if obj.status == MembershipApplication.Status.ACCEPTED:
            try:
                obj.user = obj.create_user()
            except DuplicateEmailError:
                messages.set_level(request, messages.ERROR)
                messages.error(
                    request,
                    "User with this email already exists. You can manually change the email address if you know this is really a new member.",
                )
                return
            self.send_signup_accepted_email(request, obj)
        return super().save_model(request, obj, form, change)

    def send_signup_accepted_email(self, request, obj):
        current_site = get_current_site(request)
        domain = current_site.domain
        password_reset_url = reverse(
            "password_reset_confirm",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(obj.user.pk)),
                "token": default_token_generator.make_token(obj.user),
            },
        )
        password_reset_url = f"{request.scheme}://{domain}{password_reset_url}"
        send_email(
            SignupAcceptedEmail(
                {
                    "firstname": obj.first_name,
                    "email": obj.email,
                    "password_reset_url": password_reset_url,
                }
            ),
            obj.email,
        )
