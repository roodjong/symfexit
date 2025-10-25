from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class WelcomeSupportContext(RequiredContext):
    fullname: str
    firstname: str


class WelcomeSupportTemplate(BaseTemplate[WelcomeSupportContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "welcome-support",
            _("Welcome support member template"),
            {
                "fullname": _("Full name of the member"),
                "firstname": _("First name of the member"),
            },
        )
