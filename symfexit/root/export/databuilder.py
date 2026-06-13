from collections.abc import Iterable
from datetime import datetime

from django.core.exceptions import FieldDoesNotExist
from django.db import models
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

    def build_header(self, model: type[models.Model], export_fields: fields) -> list[str]:
        header = []
        for field in export_fields:
            if isinstance(field, str):
                header.append(self.get_model_field(model, field))
            else:
                header.append(str(field[1]))
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
            row = []
            for field in export_fields:
                if isinstance(field, str):
                    value = getattr(obj, field)
                else:
                    value = getattr(obj, field[0])
                if not isinstance(value, (str, int, float, bool, type(None))):
                    value = str(value)
                row.append(value)
            rows.append(row)
        return rows
