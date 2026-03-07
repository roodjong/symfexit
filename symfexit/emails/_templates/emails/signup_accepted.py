from typing import TypedDict

from django.utils.translation import gettext_lazy as _

from symfexit.emails._templates.base import BodyTemplate


class ApplyContext(TypedDict):
    firstname: str
    email: str
    password_reset_url: str


class SignupAcceptedEmail(BodyTemplate[ApplyContext]):
    code = "signup-accepted"
    label = _("Signup accepted template")

    subject_template = "Welcome to {{site_url}}"
    html_template = """<p>Welcome to {{site_url}}!</p>

<p>Please go to the following page and choose a new password:</p>

<p><a href="{{password_reset_url}}">{{password_reset_url}}</a></p>

<p>In case you’ve forgotten, you are: {{email}}</p>

<p>Thanks for using our site!</p>

{{site_title}}"""
    text_template = """Welcome to {{site_url}}!

Please go to the following page and choose a new password:

{{password_reset_url}}

In case you’ve forgotten, you are: {{email}}

Thanks for using our site!

{{site_title}}"""

    @classmethod
    def get_input_context(cls):
        return [
            *super().get_input_context(),
            ("firstname", _("First name of the member")),
            ("email", _("Email address of the member")),
            ("password_reset_url", _("Url of the reset password link"), True),
        ]
