from typing import TypedDict

from django.utils.translation import gettext_lazy as _

from symfexit.emails._templates.base import BodyTemplate


class ApplyContext(TypedDict):
    firstname: str
    email: str
    url: str


class PasswordResetEmail(BodyTemplate[ApplyContext]):
    code = "password-reset"
    label = _("Request new password template")

    subject_template = "Password reset on {{site_url}}"
    html_template = """<p>You're receiving this email because you requested a password reset for your user account at {{ site_url }}.</p>

<p>Please go to the following page and choose a new password:</p>

<p><a href="{{url}}">{{url}}</a></p>

<p>In case you’ve forgotten, you are: {{email}}</p>

<p>Thanks for using our site!</p>

{{site_title}}"""
    text_template = """You're receiving this email because you requested a password reset for your user account at {{ site_url }}.

Please go to the following page and choose a new password:

{{url}}

In case you’ve forgotten, you are: {{email}}

Thanks for using our site!

{{site_title}}"""

    @classmethod
    def get_input_context(cls):
        return [
            *super().get_input_context(),
            ("firstname", _("First name of the member")),
            ("email", _("Email address of the member")),
            ("url", _("Url of the reset password link"), True),
        ]
