from collections.abc import Iterable
from datetime import datetime

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Manager
from django.http import HttpResponse

from symfexit.root.export.exporters._abstract_exporter import AbstractExporter
from symfexit.root.export.types import fields


class ExportDataBuilder:
    """Builder class that constructs the data to be exported based on the specified export fields and queryset."""

    def __init__(
        self,
        export_fields: fields,
        queryset: Iterable,
        model: type[models.Model],
    ):
        self.export_fields = export_fields
        self.queryset = queryset
        self.model = model

    def export(self, exporter: AbstractExporter) -> HttpResponse:
        header, rows = self.build()
        return exporter.export(header, rows, self.get_file_name())

    def get_file_name(self) -> str:
        return f"{self.model._meta.verbose_name}-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    def build(self) -> tuple[list[str], list[list[str | int | float | bool | None]]]:
        header = self.build_header(self.model, self.export_fields)
        rows = self.build_rows(self.queryset, self.export_fields)

        return header, rows

    def build_header(
        self, model: type[models.Model], export_fields: fields, prefix: str = ""
    ) -> list[str]:
        header = []
        for field in export_fields:
            if isinstance(field, str):  # get model field
                header.append(f"{prefix}{self.get_model_field(model, field)}")
            elif isinstance(field, tuple) and isinstance(
                field[1], list
            ):  # get related model field and recursively build header
                sub_model = model._meta.get_field(field[0]).related_model
                relation_label = self.get_model_field(model, field[0]).title()
                header.extend(self.build_header(sub_model, field[1], f"{prefix}{relation_label} "))
            else:
                header.append(f"{prefix}{field[1]}")
        return header

    def get_model_field(self, model: type[models.Model], field_name: str) -> str:
        # Check if it's a model field
        try:
            field = model._meta.get_field(field_name)
            return str(field.verbose_name)
        except FieldDoesNotExist:
            pass

        if hasattr(model, field_name):
            method = getattr(model, field_name)
            if hasattr(method, "short_description"):
                return str(method.short_description)

        # Fallback to field name with underscores replaced
        return field_name.replace("_", " ").title()

    def build_rows(
        self, queryset: Iterable, export_fields: fields
    ) -> list[list[str | int | float | bool | None]]:
        rows = []
        for obj in queryset:
            rows.extend(self.flatten_rows(self.build_row(obj, export_fields)))
        return rows

    def flatten_rows(self, partial_row: list) -> list[list[str | int | float | bool | None]]:
        for i, value in enumerate(partial_row):
            if isinstance(value, list):
                result = []
                prefix = partial_row[:i]
                suffix = partial_row[i + 1 :]
                for sub_row in value:
                    result.extend(self.flatten_rows(prefix + sub_row + suffix))
                return result
        return [partial_row]

    def build_row(self, obj: models.Model | None, export_fields: fields) -> list:
        row = []
        for field in export_fields:
            value = None
            if isinstance(field, tuple) and isinstance(field[1], list):
                attr, config = field
                if obj is not None:
                    value = getattr(obj, attr)
                if isinstance(value, Manager):
                    objects = list(value.all())
                    if objects:
                        row.append([self.build_row(sub_obj, config) for sub_obj in objects])
                        continue
                    value = None
                row.extend(self.build_row(value, config))
                continue

            if obj is not None:  # make nested fields of null objects also null
                if isinstance(field, str):  # field only
                    value = getattr(obj, field)
                elif isinstance(field, tuple):  # field with label
                    value = getattr(obj, field[0])
            if not isinstance(value, (str, int, float, bool, type(None))):
                value = str(value)
            row.append(value)
        return row
