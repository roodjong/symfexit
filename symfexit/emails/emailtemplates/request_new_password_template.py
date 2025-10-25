from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class RequestNewPasswordContext(RequiredContext):
    firstname: str
    url: str


class RequestNewPasswordTemplate(BaseTemplate[RequestNewPasswordContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "password-reset",
            _("Request new password template"),
            {
                "firstname": _("First name of the member"),
                "url": _("Url of the reset password link"),
            },
            ["url"],
        )
