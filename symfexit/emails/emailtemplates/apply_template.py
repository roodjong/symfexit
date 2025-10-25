from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class ApplyContext(RequiredContext):
    firstname: str


class ApplyTemplate(BaseTemplate[ApplyContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "apply",
            _("Apply template"),
            {"firstname": _("Firstname of the member")},
        )
