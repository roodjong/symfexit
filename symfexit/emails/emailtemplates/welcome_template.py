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
    password_url: str
    member_id: str


class WelcomeTemplate(BaseTemplate[WelcomeContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "welcome",
            _("Welcome template"),
            {
                "fullname": _("Full name of the user"),
                "firstname": _("First name of the user"),
                "member_id": _("Login member id"),
                "group": _("Group user is in"),
                "nextevent": _("Next event"),
                "password_url": _("Password reset url"),
            },
            ["password_url"],
        )

    def get_base_context(self):
        return {
            **super().get_base_context(),
            # nextevent: Events.objects.filter(startdate > now).first().tostring()
        }
