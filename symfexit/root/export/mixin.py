from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from symfexit.root.export.databuilder import ExportDataBuilder
from symfexit.root.export.exporters.json_exporter import JsonExporter
from symfexit.root.export.types import fields


class ExportMixin(admin.ModelAdmin):
    """
    Mixin for Django admin classes that adds data export functionality.
    It defines the export fields and handles the export action.

    Place it for the admin.ModelAdmin class of the model you want to export.


    `export_fields` attribute, which can be a list of field names or
        tuples of (field_name, header_name).
    """

    export_fields: fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.export_fields:
            raise ValueError("export_fields must be defined in the admin class.")

        # add action to list of actions
        actions_list = list(self.actions or [])
        if "export_data" not in actions_list:
            actions_list.append("export_data")
        self.actions = tuple(actions_list)

    @admin.action(description=_("Export selected data"))
    def export_data(self, request: HttpRequest, queryset: models.QuerySet) -> HttpResponse:
        """Admin action that handles the export process, including permission checks and data retrieval."""

        # check permissions
        if not self.has_export_permission(request):
            messages.error(request, _("You don't have permission to export data."))
            return redirect(request.META.get("HTTP_REFERER", "admin:index"))

        if not queryset.exists():
            messages.warning(request, _("No rows selected for export."))
            return redirect(request.META.get("HTTP_REFERER", "admin:index"))

        # export data
        return ExportDataBuilder(self.export_fields, queryset, self.model).export(JsonExporter())

    def has_export_permission(self, request: HttpRequest) -> bool:
        """Check if the user has permission to export data. By default, it checks if the user has view permission."""
        return self.has_view_permission(request)
