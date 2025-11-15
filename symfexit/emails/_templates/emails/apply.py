from typing import TypedDict

from django.utils.translation import gettext_lazy as _

from symfexit.emails._templates.base import BodyTemplate


class ApplyContext(TypedDict):
    firstname: str


class ApplyEmail(BodyTemplate[ApplyContext]):
    code = "apply"
    label = _("Apply template")

    subject_template = "Applied"
    html_template = "You succesfully applied"
    text_template = "You succesfully applied"

    @classmethod
    def get_input_context(cls):
        return [
            *super().get_input_context(),
            {"firstname": _("First name of the member")},
        ]

    pass
