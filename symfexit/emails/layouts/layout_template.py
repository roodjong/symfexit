from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseTemplate,
    GivenContext,
    RequiredContext,
)


class LayoutContext(RequiredContext):
    content: str


class LayoutTemplate(BaseTemplate[LayoutContext, GivenContext]):
    def __init__(self):
        super().__init__(
            "layout",
            _("Layout template"),
            {"content": _("Main of the email")},
        )

    # validate??? maybe require content
