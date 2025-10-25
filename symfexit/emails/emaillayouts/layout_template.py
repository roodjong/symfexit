from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import (
    BaseLayout,
    GivenContext,
)


class LayoutContext(GivenContext):
    content: str


class LayoutTemplate(BaseLayout[LayoutContext]):
    def __init__(self):
        super().__init__(
            "layout", _("Layout template"), {"content": _("Main of the email")}, ("content",)
        )
