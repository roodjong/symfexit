from __future__ import annotations

from typing import TYPE_CHECKING

from symfexit.emails._templates.base import BaseEmailComponent, WrapperLayout
from symfexit.emails._templates.emails.membership_application import MembershipApplicationEmail
from symfexit.emails._templates.emails.password_request import PasswordResetEmail
from symfexit.emails._templates.layouts.base import BaseLayout

if TYPE_CHECKING:
    from .base import BodyTemplate


class BaseManager:
    _registry: list[type[BaseEmailComponent]]

    @classmethod
    def get_as_choices(cls) -> list[tuple[str, str]]:
        return [(e.code, e.label) for e in cls._registry]

    @classmethod
    def find(cls, code: str) -> type[BodyTemplate] | None:
        for e in cls._registry:
            if e.code == code:
                return e
        return None


class EmailTemplateManager(BaseManager):
    _registry: list[type[BodyTemplate]] = [MembershipApplicationEmail, PasswordResetEmail]


class EmailLayoutManager(BaseManager):
    _registry: list[type[WrapperLayout]] = [BaseLayout]
