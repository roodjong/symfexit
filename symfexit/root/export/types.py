from collections.abc import Callable, Sequence

from django.db import models

type field_with_label = tuple[str, str]
type field_with_label_and_lambda = tuple[
    str, str, Callable[[models.Model], str | int | float | bool | None]
]
type field_with_model = tuple[str, fields]
type fields = Sequence[str | field_with_label | field_with_label_and_lambda | field_with_model]
