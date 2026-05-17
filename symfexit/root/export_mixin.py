from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

# Constants for field path handling
EXPORT_SESSION_KEY_TEMPLATE = "export_ids_{app_label}_{model_name}"
EXPORT_FIELD_SEPARATOR = "__"
EXPORT_COUNT_SUFFIX = "__count"


class ExportMixin(admin.ModelAdmin):
    """
    Mixin for Django ModelAdmin classes to add CSV/Excel export functionality.

    This mixin adds an admin action that allows users to export selected rows
    to CSV or Excel format with customizable field selection. The export process
    uses a two-step workflow: first, users select rows in the admin changelist,
    then they choose which fields to include and the desired export format.

    Configuration Attributes:
        export_fields (list[str] | None): List of field names to include in export.
            These are the ONLY fields available for export. If None or empty,
            no fields will be available (export action will have no fields to select).
            Always explicitly define which fields should be exportable.
            Default: None

        export_field_labels (dict[str, str]): Custom display labels for fields.
            Maps field names to translated strings that override verbose_name.
            Example: {'created_at': _('Date Created')}
            Default: {}

        export_model_config (list[tuple]): Configuration for expandable relationships.
            Each tuple is (field_name, config) where config is either:
            - A ModelAdmin class reference: Uses that admin's export configuration (DRY)
            - A list of field names: Explicit field list for the related model

            Supports nested relationships via admin references.
            Example: [
                ('attendees', UserAdmin),  # UserAdmin may also have export_model_config
                ('categories', ['name', 'description']),  # Explicit field list
            ]
            Default: []

    Example:
        >>> class EventAdmin(ExportMixin, admin.ModelAdmin):
        ...     export_fields = ['name', 'date', 'organizer', 'attendees']
        ...     export_field_labels = {
        ...         'name': _('Event Name'),
        ...         'date': _('Event Date'),
        ...     }
        ...     export_model_config = [
        ...         ('attendees', UserAdmin),  # Reuse UserAdmin's export config
        ...     ]
        ...
        ...     def get_export_queryset(self, request, ids):
        ...         # Optimize query for export
        ...         qs = super().get_export_queryset(request, ids)
        ...         return qs.prefetch_related('attendees__groups')

    Overridable Methods:
        - get_export_fields(): Customize which fields are available
        - get_export_field_label(): Customize field label generation
        - format_export_value(): Customize value formatting per field/type
        - get_export_queryset(): Optimize queryset (add prefetch_related, etc)
        - has_export_permission(): Add custom permission logic
    """

    # Configuration attributes - override these in your admin class
    export_fields: list[str] | None = None
    export_field_labels: dict[str, str | Any] = {}
    export_model_config: list[tuple[str, list[str] | type[ExportMixin]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the mixin and register the export_data action.

        This ensures the export action appears in the admin changelist
        actions dropdown.
        """
        super().__init__(*args, **kwargs)

        # Convert actions to list if it's a tuple, and add export_data
        if self.actions is None:
            self.actions = ["export_data"]
        elif isinstance(self.actions, (list, tuple)):
            # Convert to list and add our action
            actions_list = list(self.actions)
            if "export_data" not in actions_list:
                actions_list.append("export_data")
            self.actions = actions_list

    @admin.action(description=_("Export selected data"))
    def export_data(self, request: HttpRequest, queryset: models.QuerySet) -> HttpResponse:
        """
        Admin action that initiates the export process.

        This is the entry point for exports. It:
        1. Checks if user has export permission
        2. Collects IDs of selected objects
        3. Stores IDs in session (avoids URL length limits)
        4. Redirects to field selection page

        Args:
            request: The HTTP request object
            queryset: QuerySet of selected objects to export

        Returns:
            HttpResponse redirecting to the field selection page
        """
        # Check permissions
        if not self.has_export_permission(request):
            messages.error(request, _("You don't have permission to export data."))
            return redirect(request.META.get("HTTP_REFERER", "admin:index"))

        # Get the IDs of selected objects
        selected_ids = list(queryset.values_list("pk", flat=True))

        if not selected_ids:
            messages.warning(request, _("No objects selected for export."))
            return redirect(request.META.get("HTTP_REFERER", "admin:index"))

        # Store IDs in session to avoid URL length limitations
        # Use a unique session key that includes the model info
        app_label = self.model._meta.app_label  # type: ignore[attr-defined]
        model_name = self.model._meta.model_name  # type: ignore[attr-defined]
        session_key = EXPORT_SESSION_KEY_TEMPLATE.format(app_label=app_label, model_name=model_name)
        request.session[session_key] = selected_ids  # type: ignore[attr-defined]

        # Build URL to the export field selection view
        export_url = reverse(
            "export_field_selection",
            kwargs={
                "app_label": app_label,
                "model_name": model_name,
            },
        )

        # Redirect to field selection page
        return redirect(export_url)

    def has_export_permission(self, request: HttpRequest) -> bool:
        """
        Check if the user has permission to export data.

        By default, checks for view permission on the model.
        Override this method for custom permission logic.
        """
        return self.has_view_permission(request)  # type: ignore[attr-defined]

    def get_export_fields(self) -> list[str]:
        """Get the list of fields available for export."""
        if self.export_fields:
            return list(self.export_fields)

        return []

    def get_export_field_label(self, field_name: str) -> str:
        """Get the display label for a field in the export."""
        # Handle count field (e.g., "attendees__count")
        if field_name.endswith(EXPORT_COUNT_SUFFIX):
            base_field_name = field_name[: -len(EXPORT_COUNT_SUFFIX)]
            field = self.model._meta.get_field(base_field_name)  # type: ignore[attr-defined]
            return f"{str(field.verbose_name)} ({str(_('count'))})"

        # Check for custom label
        if field_name in self.export_field_labels:
            return str(self.export_field_labels[field_name])

        # Check if it's a model field
        try:
            field = self.model._meta.get_field(field_name)  # type: ignore[attr-defined]
            return str(field.verbose_name)
        except FieldDoesNotExist:
            pass

        # Check if it's a method on the admin or model
        if hasattr(self, field_name):
            method = getattr(self, field_name)
            if hasattr(method, "short_description"):
                return str(method.short_description)

        if hasattr(self.model, field_name):  # type: ignore[attr-defined]
            method = getattr(self.model, field_name)  # type: ignore[attr-defined]
            if hasattr(method, "short_description"):
                return str(method.short_description)

        # Fallback to field name with underscores replaced
        return field_name.replace("_", " ").title()

    def format_export_value(self, obj: models.Model, field_name: str) -> str:
        """Format a field value for export."""
        # Handle count field (e.g., "attendees__count")
        if field_name.endswith(EXPORT_COUNT_SUFFIX):
            base_field_name = field_name[: -len(EXPORT_COUNT_SUFFIX)]
            related_manager = getattr(obj, base_field_name)
            if hasattr(related_manager, "count"):
                return str(related_manager.count())
            return "0"

        # Try to get the value
        value = None

        # Check if it's a method on the admin class
        if hasattr(self, field_name):
            method = getattr(self, field_name)
            if callable(method):
                value = method(obj)

        # Check if it's a method or attribute on the model
        if value is None and hasattr(obj, field_name):
            attr = getattr(obj, field_name)
            # Check if it's a related manager (has .all() method) - don't call it
            if hasattr(attr, "all"):
                value = attr
            elif callable(attr):
                value = attr()
            else:
                value = attr

        # Handle None
        if value is None:
            return ""

        # Try to get field metadata for type-specific handling
        # This may fail if field_name is an admin method rather than a model field
        try:
            field = self.model._meta.get_field(field_name)  # type: ignore[attr-defined]

            # Handle ForeignKey
            if isinstance(field, models.ForeignKey):
                return str(value) if value else ""

            # Handle ManyToMany
            if isinstance(field, models.ManyToManyField):
                if hasattr(value, "all"):
                    return ", ".join(str(item) for item in value.all())
                return str(value)

            # Handle Boolean
            if isinstance(field, models.BooleanField):
                return str(_("Yes")) if value else str(_("No"))

            # Handle Date
            if isinstance(field, models.DateField) and isinstance(value, (date, datetime)):
                return str(date_format(value, "SHORT_DATE_FORMAT"))

            # Handle DateTime
            if isinstance(field, models.DateTimeField) and isinstance(value, datetime):
                return str(date_format(value, "SHORT_DATETIME_FORMAT"))
        except FieldDoesNotExist:
            # Field is an admin method or callable, not a model field
            pass

        return str(value)

    def get_export_queryset(self, request: HttpRequest, ids: list[int]) -> models.QuerySet:
        """
        Get the queryset for export with the specified IDs.

        This method can be overridden to optimize the export queryset with
        select_related() or prefetch_related() for better performance,
        especially when exporting ForeignKey or ManyToMany fields.

        The queryset respects the admin's get_queryset() method, so any
        row-level filtering applied there will be honored.

        Args:
            request: The HTTP request object
            ids: List of primary keys to export

        Returns:
            QuerySet of objects to export

        Example:
            Override for performance optimization:

            >>> def get_export_queryset(self, request, ids):
            ...     queryset = super().get_export_queryset(request, ids)
            ...     return queryset.select_related('author', 'category') \\
            ...                     .prefetch_related('tags', 'comments')
        """
        queryset = self.get_queryset(request)  # type: ignore[attr-defined]
        return queryset.filter(pk__in=ids)

    def get_expandable_fields(self) -> dict[str, tuple[models.Field, list[str]]]:
        """
        Get fields that can be expanded (M2M or 1-to-many) from export_model_config.

        Recursively processes nested export_model_config from referenced admin classes.
        For example, if EventsAdmin references UserAdmin which has its own export_model_config,
        those nested expandables are included with prefixed paths (e.g., attendees__groups).

        Returns:
            Dict mapping field names to (field_object, related_fields_list)

        Example:
            >>> expandable = self.get_expandable_fields()
            >>> # {'attendees': (<ManyToManyField>, ['email', 'first_name']),
            >>> #  'attendees__groups': (<ManyToManyField>, ['name'])}
        """

        def process_config(current_model, config, prefix=""):
            """
            Recursively process export_model_config.

            Args:
                current_model: The model class to process fields on
                config: The export_model_config list
                prefix: Field path prefix (e.g., "attendees__")

            Returns:
                Dict of expandable fields
            """
            result = {}

            for field_path, related_fields in config:
                full_field_path = f"{prefix}{field_path}" if prefix else field_path

                # Skip if already contains __ (manually specified nested path)
                if EXPORT_FIELD_SEPARATOR in field_path:
                    continue

                # Resolve related_fields: could be a list or an admin class
                resolved_fields = None
                nested_admin = None

                if isinstance(related_fields, list):
                    # It's already a list of field names
                    resolved_fields = related_fields
                elif hasattr(related_fields, "export_fields"):
                    # It's an admin class, extract its export_fields
                    resolved_fields = related_fields.export_fields
                    # Check if it has nested export_model_config
                    if (
                        hasattr(related_fields, "export_model_config")
                        and related_fields.export_model_config
                    ):
                        nested_admin = related_fields
                else:
                    # Use it as-is (must be an iterable)
                    resolved_fields = list(related_fields)

                if resolved_fields is None:
                    continue

                # Get the field from the current model
                field = current_model._meta.get_field(field_path)
                # Check if it's a M2M or reverse FK (1-to-many)
                if isinstance(field, models.ManyToManyField) or (
                    isinstance(field, models.ManyToOneRel)
                ):
                    result[full_field_path] = (field, resolved_fields)

                    # If we have a nested admin with its own config, process it recursively
                    if nested_admin:
                        related_model = self.get_related_model(field)
                        if related_model:
                            nested_config = nested_admin.export_model_config
                            nested_prefix = f"{full_field_path}{EXPORT_FIELD_SEPARATOR}"
                            nested_expandables = process_config(
                                related_model, nested_config, nested_prefix
                            )
                            result.update(nested_expandables)

            return result

        if not self.export_model_config:
            return {}

        return process_config(self.model, self.export_model_config)  # type: ignore[attr-defined]

    def get_related_field_label(self, related_model: type[models.Model], field_name: str) -> str:
        """
        Get the label for a field on a related model.

        Used when building field selection UI for expandable relationships.

        Args:
            related_model: The related model class
            field_name: The field name on the related model

        Returns:
            Human-readable label for the field
        """
        field = related_model._meta.get_field(field_name)
        return str(field.verbose_name)

    def get_related_model(self, field: models.Field) -> type[models.Model] | None:
        """
        Get the related model for a M2M or 1-to-many field.

        Args:
            field: The field object (ManyToManyField or ManyToOneRel)

        Returns:
            Related model class or None
        """
        if isinstance(field, models.ManyToManyField):
            return field.related_model
        elif isinstance(field, models.ManyToOneRel):
            return field.related_model
        return None
