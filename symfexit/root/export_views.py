from __future__ import annotations

import json
import logging
from datetime import datetime

from django.apps import apps
from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View

from symfexit.root.export_builder import ExportDataBuilder
from symfexit.root.export_formatters import get_formatter
from symfexit.root.export_mixin import EXPORT_SESSION_KEY_TEMPLATE


@method_decorator(staff_member_required, name="dispatch")
class ExportFieldSelectionView(View):
    """
    View for field selection and export generation.

    GET: Displays a form with checkboxes for each available export field
    POST: Generates and returns the export file (CSV or Excel)
    """

    def setup(self, request, *args, **kwargs):
        """Initialize view with model, admin_class, and session IDs."""
        super().setup(request, *args, **kwargs)

        app_label = kwargs["app_label"]
        model_name = kwargs["model_name"]

        # Get model and admin class
        self.model = apps.get_model(app_label, model_name)
        self.admin_class = admin.site._registry.get(self.model)

        # Get selected IDs from session
        self.session_key = EXPORT_SESSION_KEY_TEMPLATE.format(
            app_label=app_label, model_name=model_name
        )
        self.ids = request.session.get(self.session_key)

    def dispatch(self, request, *args, **kwargs):
        """Check prerequisites before dispatching to get/post."""
        # Validate admin class exists
        if not self.admin_class:
            return HttpResponse("Invalid request", status=400, content_type="text/plain")

        # Check permissions
        if not self.admin_class.has_export_permission(request):
            return HttpResponse("Permission denied", status=403, content_type="text/plain")

        # Check IDs exist
        if not self.ids:
            changelist_url = reverse(
                f"admin:{kwargs['app_label']}_{kwargs['model_name']}_changelist"
            )
            return redirect(changelist_url)

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, app_label, model_name):
        """
        Display the field selection form.

        Shows:
        - List of base fields with checkboxes
        - Expandable relationship fields with nested options
        - Count field options for relationships
        - Format selection (CSV/Excel)
        """
        # Get available export fields
        export_fields = self.admin_class.get_export_fields()

        # Get expandable fields from config
        expandable_fields = self.admin_class.get_expandable_fields()

        def build_field_info(field_path: str, field_name: str) -> dict:
            """Recursively build field info with expandable nested fields."""
            label = self.admin_class.get_export_field_label(field_path)

            field_info = {
                "name": field_name,
                "label": label,
            }

            # Check if this field is expandable
            if field_path in expandable_fields:
                field_obj, related_fields = expandable_fields[field_path]
                related_model = self.admin_class.get_related_model(field_obj)

                if related_model:
                    # Recursively build each related field - recursion handles all nesting
                    related_field_info = []
                    for related_field_name in related_fields:
                        nested_field_path = f"{field_path}__{related_field_name}"
                        nested_field = build_field_info(nested_field_path, related_field_name)
                        nested_field["full_name"] = nested_field_path
                        related_field_info.append(nested_field)

                    field_info["is_expandable"] = True
                    field_info["expandable_info"] = {
                        "related_model": related_model._meta.verbose_name_plural,
                        "fields": related_field_info,
                    }
                    field_info["count_field"] = f"{field_path}__count"

            return field_info

        # Build field choices with labels and expansion info
        field_choices = []
        for field_name in export_fields:
            field_choices.append(build_field_info(field_name, field_name))

        # Get count of selected objects
        queryset = self.admin_class.get_export_queryset(request, self.ids)
        object_count = queryset.count()

        context = {
            "title": _("Export %(model)s") % {"model": self.model._meta.verbose_name_plural},
            "model_name": self.model._meta.verbose_name_plural,
            "object_count": object_count,
            "field_choices": field_choices,
            "app_label": app_label,
            "model_name_url": model_name,
            "opts": self.model._meta,
            "has_view_permission": True,
            "site_title": admin.site.site_title,
            "site_header": admin.site.site_header,
        }

        return render(request, "admin/export_field_selection.html", context)

    def post(self, request, app_label, model_name):
        """
        Generate and return the export file.

        This handles two types of POST requests:
        1. Initial POST with field selection -> returns loading page
        2. Download POST from loading page -> generates and returns file
        """
        # Get selected fields
        selected_fields = request.POST.getlist("fields")
        if not selected_fields:
            return HttpResponse("No fields selected", status=400)

        # Check if this is the actual download request
        if request.POST.get("download") == "true":
            # Get export format
            export_format = request.POST.get("format", "csv")

            # Get the queryset
            queryset = self.admin_class.get_export_queryset(request, self.ids)
            object_count = queryset.count()

            # Log the export action using Django's built-in admin logging
            content_type = ContentType.objects.get_for_model(self.model)
            LogEntry.objects.create(
                user_id=request.user.pk,
                content_type_id=content_type.pk,
                object_id=str(self.ids[0]) if len(self.ids) == 1 else "",
                object_repr=f"Exported {object_count} {self.model._meta.verbose_name_plural}",
                action_flag=CHANGE,
                change_message=json.dumps(
                    {
                        "export": {
                            "format": export_format,
                            "fields": selected_fields,
                            "count": object_count,
                            "timestamp": datetime.now().isoformat(),
                        }
                    }
                ),
            )

            # Clean up session data after successful export
            del request.session[self.session_key]

            # Generate and return file
            try:
                return self._generate_export(queryset, selected_fields, export_format)
            except Exception as e:
                # Log the error and return friendly message
                logger = logging.getLogger(__name__)
                logger.error(f"Export generation failed: {e}", exc_info=True)
                return HttpResponse(
                    "An internal error occurred while generating the export.", status=500
                )

        # Return HTML page that shows spinner and fetches file via AJAX
        export_format = request.POST.get("format", "csv")
        changelist_url = reverse(f"admin:{app_label}_{model_name}_changelist")
        export_url = reverse(
            "export_field_selection", kwargs={"app_label": app_label, "model_name": model_name}
        )

        # Prepare context for loading page template
        context = {
            "export_format": export_format,
            "export_url": export_url,
            "changelist_url": changelist_url,
            "selected_fields_json": json.dumps(selected_fields),
        }

        return render(request, "admin/export_loading.html", context)

    def _generate_export(self, queryset, fields: list[str], export_format: str) -> HttpResponse:
        """
        Generate the export file using the data builder and formatter.

        This method coordinates the three layers:
        1. Business Logic: ExportDataBuilder transforms queryset to headers/rows
        2. Presentation: ExportFormatter generates format-specific output

        Args:
            queryset: The queryset to export
            fields: List of field names to include
            export_format: Format type ('csv' or 'excel')

        Returns:
            HttpResponse with the export file
        """
        # Build structured data (headers + rows)
        builder = ExportDataBuilder(self.admin_class, self.model, queryset, fields)
        headers = builder.build_headers()
        rows = builder.build_rows()

        # Get the appropriate formatter
        formatter = get_formatter(export_format)

        # Generate and return the file
        filename_base = str(self.model._meta.verbose_name_plural).replace(" ", "_")
        return formatter.format(headers, rows, filename_base)
