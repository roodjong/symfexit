from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class WelcomeContext(RequiredContext):
    fullname: str
    firstname: str
    group: str
    nextevent: str
    url: str
    member_id: str


class WelcomeTemplate(BaseTemplate[WelcomeContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "welcome",
            _("Welcome template"),
            {
                "fullname": _("Full name of the member"),
                "firstname": _("First name of the member"),
                "member_id": _("Login member id"),
                "group": _("Group member is in"),
                "url": _("Password reset url"),
            },
            ["url"],
        )
