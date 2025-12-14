import re
import urllib.parse
from dataclasses import dataclass
from typing import ClassVar, TypedDict, TypeVar

from constance import config
from django.utils.translation import gettext_lazy as _

from symfexit.root import settings


class BaseContext(TypedDict):
    site_title: str
    full_date_time: str


T = TypeVar("T", bound=BaseContext)

BASE_CONTEXT_KEY_LENGTH = 4
INPUT_CONTEXT_KEY_LENGTH = 3


class BaseEmailComponent[T]:
    label: ClassVar[str]
    code: ClassVar[str]
    description: ClassVar[str]
    context: dict

    def __init__(self, context: T):
        self.context = {**self.get_context_values(), **context}

    @classmethod
    def get_base_context(cls):
        """Content that is global and for every email the same."""
        return [
            ("site_title", _("Main title of this site"), config.SITE_TITLE),
            ("site_url", _("Main site of the organisation"), config.MAIN_SITE),
            (
                "site_logo",
                _("Organisation logo"),
                f"{config.MAIN_SITE}/{settings.MEDIA_URL}{config.LOGO_IMAGE}",
            ),
        ]

    @classmethod
    def get_context_values(self):
        return {c[0]: c[2] for c in self.get_base_context()}

    @classmethod
    def get_context_options(self):
        return {
            **{
                c[0]: (c[1], c[3] if len(c) > BASE_CONTEXT_KEY_LENGTH - 1 else False)
                for c in self.get_base_context()
            },
            **{
                c[0]: (c[1], c[2] if len(c) > INPUT_CONTEXT_KEY_LENGTH - 1 else False)
                for c in self.get_input_context()
            },
        }

    @classmethod
    def get_input_context(cls):
        """(code, label, required=False)"""
        return []

    @dataclass
    class TemplateValidation:
        formatted_template: str
        unknown_context_keys: list[str]
        missing_context_keys: list[str]

    @classmethod
    def validate_template(cls, template_text) -> TemplateValidation:
        # Check if used keys are correctly spelled, if not return list of all possible and also return wrongly spelled/missing keys
        all_keys = []
        required_keys = []
        unknown_keys = []

        for key_data in cls.get_base_context():
            all_keys.append(key_data[0])
            if len(key_data) == BASE_CONTEXT_KEY_LENGTH:
                required_keys.append(key_data[0])

        for key_data in cls.get_input_context():
            all_keys.append(key_data[0])
            if len(key_data) == INPUT_CONTEXT_KEY_LENGTH:
                if key_data[2]:
                    required_keys.append(key_data[0])

        template_text = urllib.parse.unquote(template_text)

        # Replace function
        def replace_keys(match):
            key = match.group(1).strip()  # Get the captured group and trim whitespace
            return f"{{{{ {key} }}}}"  # Format it to {{ key }}

        # Perform the replacement
        matches = re.findall(r"{{\s*(.*?)\s*}}", template_text)
        formatted_template = re.sub(r"{{\s*(.*?)\s*}}", replace_keys, template_text)

        for m in matches:
            if m in required_keys:
                required_keys.remove(m)
            if m not in all_keys:
                unknown_keys.append(m)

        return BaseEmailComponent.TemplateValidation(
            formatted_template, unknown_keys, required_keys
        )


class LayoutContext(TypedDict):
    content: str


LayoutContextType = TypeVar("LayoutContextType", bound=LayoutContext)


class WrapperLayout[LayoutContext](BaseEmailComponent[LayoutContext]):
    @classmethod
    def get_input_context(cls):
        return [
            *super().get_input_context(),
            ("content", _("Email template outlet"), True),
        ]


class BodyTemplate[T](BaseEmailComponent[T]):
    subject_template: ClassVar[str]
    html_template: ClassVar[str]
    text_template: ClassVar[str]
    pass
