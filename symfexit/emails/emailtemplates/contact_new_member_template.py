from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class ContactNewMemberContext(RequiredContext):
    firstname: str
    fullname: str
    division: str


class ContactNewMemberTemplate(BaseTemplate[ContactNewMemberContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "contact_new_member",
            _("Contact a new member template"),
            {
                "firstname": _("First name of the member"),
                "fullname": _("Full name of the member"),
                "division": _("Name of the division"),
            },
        )
