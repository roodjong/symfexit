# symfexit/root/views.py
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetView
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from symfexit.emails._templates.emails.password_request import PasswordResetEmail
from symfexit.emails._templates.render import send_email
from symfexit.members.admin import Member


class MyPasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        # context = {
        #     "email": user_email,
        #     "domain": domain,
        #     "site_name": site_name,
        #     "uid": urlsafe_base64_encode(user_pk_bytes),
        #     "user": user,
        #     "token": token_generator.make_token(user),
        #     "protocol": "https" if use_https else "http",
        #     **(extra_email_context or {}),
        # }
        user: Member = context["user"]
        reset_path = reverse(
            "password_reset_confirm",  # your URL‑conf name
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )

        # # Prepend scheme+host to make a full absolute URL
        reset_url = f"{context['protocol']}://{context['domain']}{reset_path}"
        send_email(
            PasswordResetEmail(
                {
                    "firstname": user.first_name,
                    "url": reset_url,
                    "email": user.email,
                }
            ),
            recipient_list=[to_email],
        )


class CustomPasswordResetView(PasswordResetView):
    form_class = MyPasswordResetForm
