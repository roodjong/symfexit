from __future__ import annotations

from django.db import models
from django.utils.translation import gettext as _

# Constants matching export_mixin.py
EXPORT_FIELD_SEPARATOR = "__"
EXPORT_COUNT_SUFFIX = "__count"


class FieldExpansion:
    """
    Represents an expandable field (M2M or 1-to-many) with its configuration.

    Attributes:
        field_path: Full path to the field (e.g., "attendees" or "attendees__groups")
        field_obj: The Django field object (ManyToManyField or ManyToOneRel)
        sub_fields: List of field names to include from the related model
    """

    def __init__(self, field_path: str, field_obj: models.Field, sub_fields: list[str]):
        self.field_path = field_path
        self.field_obj = field_obj
        self.sub_fields = sub_fields
        self.parts = field_path.split(EXPORT_FIELD_SEPARATOR)

    @property
    def relation_name(self) -> str:
        """Get the last part of the field path (the actual relation name)."""
        return self.parts[-1]

    @property
    def count_field_name(self) -> str:
        """Get the full field name for count display (e.g., 'attendees__count')."""
        return f"{self.field_path}{EXPORT_COUNT_SUFFIX}"


class ExportDataBuilder:
    """
    Builds structured export data from Django querysets.

    Takes a queryset and field configuration, produces headers and rows
    ready for formatting by ExportFormatter implementations.
    """

    def __init__(self, admin_class, model, queryset, fields: list[str]):
        """
        Initialize the data builder.

        Args:
            admin_class: The ModelAdmin instance (provides formatting and labels)
            model: The model class being exported
            queryset: The queryset containing objects to export
            fields: List of field names to include in export (may include
                   nested paths like 'attendees__email' or count fields
                   like 'attendees__count')
        """
        self.admin_class = admin_class
        self.model = model
        self.queryset = queryset
        self.fields = fields

        # Separate expanded fields from simple fields
        self.expanded_fields = [
            f for f in fields if EXPORT_FIELD_SEPARATOR in f and not f.endswith(EXPORT_COUNT_SUFFIX)
        ]
        self.base_fields = [f for f in fields if f not in self.expanded_fields]

        # Get expansion metadata from admin class
        self.expansions = self._build_expansion_map()

    def _build_expansion_map(self) -> dict[str, FieldExpansion]:
        """
        Build a map of field paths to their expansion metadata.

        Uses the admin class's get_expandable_fields() method to get configuration
        for M2M and 1-to-many relationships.

        Returns:
            Dict mapping field_path to FieldExpansion objects
        """
        if not hasattr(self.admin_class, "get_expandable_fields"):
            return {}

        expandable = self.admin_class.get_expandable_fields()
        result = {}

        # Only include expansions that are actually used in expanded_fields
        for field_path, (field_obj, sub_fields) in expandable.items():
            # Check if any expanded field starts with this path
            if any(
                ef.startswith(field_path + EXPORT_FIELD_SEPARATOR)
                or ef.split(EXPORT_FIELD_SEPARATOR)[0] == field_path
                for ef in self.expanded_fields
            ):
                result[field_path] = FieldExpansion(field_path, field_obj, sub_fields)

        return result

    def has_expansion(self) -> bool:
        """Check if any fields use relationship expansion."""
        return len(self.expanded_fields) > 0

    def build_headers(self) -> list[str]:
        """
        Build the header row for export with translated labels.

        Headers are built in the same order as data will appear:
        1. Base fields (non-expanded)
        2. Count fields interleaved with their expansions
        3. Expanded field headers in tree traversal order

        Returns:
            List of translated header labels
        """
        headers = []

        # Add non-expanded base field headers
        for field in self.base_fields:
            # Skip count fields that correspond to expanded relations
            # They'll be added inline with their expansions
            if field.endswith(EXPORT_COUNT_SUFFIX) and self.has_expansion():
                relation_path = field[: -len(EXPORT_COUNT_SUFFIX)]
                if any(
                    ef.startswith(relation_path + EXPORT_FIELD_SEPARATOR)
                    for ef in self.expanded_fields
                ):
                    continue

            headers.append(self._get_field_label(field))

        # Add expanded field headers
        if self.has_expansion():
            headers.extend(self._build_expansion_headers())

        return headers

    def _build_expansion_headers(self) -> list[str]:
        """
        Build headers for expanded fields in the same order as data.

        This method builds headers that match the structure created by
        _build_expanded_rows(), ensuring header-data alignment.
        """
        expansion_structure = self._build_expansion_structure()
        return self._build_headers_recursively(expansion_structure, self.base_fields, "")

    def _build_headers_recursively(
        self, expansion_tree: dict, base_fields: list[str], prefix: str
    ) -> list[str]:
        """
        Recursively build headers matching the data structure.

        Args:
            expansion_tree: Nested dict structure of expansions
            base_fields: List of all base fields (for finding count fields)
            prefix: Current field path prefix for nested relations

        Returns:
            List of header labels in the correct order
        """
        headers = []

        for relation_name, relation_config in expansion_tree.items():
            relation_path = f"{prefix}{relation_name}" if prefix else relation_name
            count_field = f"{relation_path}{EXPORT_COUNT_SUFFIX}"

            # Add count field header if it was requested
            if count_field in base_fields:
                headers.append(self._get_field_label(count_field))

            # Add headers for fields at this level
            for full_field, _field_name in relation_config["fields"]:
                headers.append(self._get_field_label(full_field))

            # Recursively add nested headers
            if relation_config["nested"]:
                nested_headers = self._build_headers_recursively(
                    relation_config["nested"],
                    base_fields,
                    f"{relation_path}{EXPORT_FIELD_SEPARATOR}",
                )
                headers.extend(nested_headers)

        return headers

    def _get_field_label(self, field_name: str) -> str:
        """
        Get the display label for a field.

        Delegates to admin class for custom labeling logic.
        Handles both simple fields and nested field paths.
        """
        if EXPORT_FIELD_SEPARATOR in field_name:
            return self._get_nested_field_label(field_name)
        return self.admin_class.get_export_field_label(field_name)

    def _get_nested_field_label(self, field_path: str) -> str:
        """
        Get label for nested field path like 'attendees__groups__name'.

        Traverses the relationship chain and concatenates verbose names.
        Examples:
        - 'attendees__email' -> "attendees email"
        - 'attendees__groups__name' -> "attendees groups name"
        - 'attendees__count' -> "attendees (count)"

        Args:
            field_path: Nested field path with __ separators

        Returns:
            Human-readable label with relationship names prepended
        """
        is_count = field_path.endswith(EXPORT_COUNT_SUFFIX)
        if is_count:
            field_path = field_path[: -len(EXPORT_COUNT_SUFFIX)]

        parts = field_path.split(EXPORT_FIELD_SEPARATOR)
        current_model = self.model
        labels = []

        # Traverse relationships and collect verbose names
        for part in parts[:-1]:
            field = current_model._meta.get_field(part)
            labels.append(str(field.verbose_name))
            current_model = self.admin_class.get_related_model(field)
            if not current_model:
                raise ValueError(
                    f"Could not resolve related model for field '{part}' in path '{field_path}'"
                )

        # Get label for the final field
        final_field = parts[-1]
        field = current_model._meta.get_field(final_field)
        labels.append(str(field.verbose_name))

        result = " ".join(labels)

        # Add count suffix if this is a count field
        if is_count:
            result += f" ({str(_('count'))})"

        return result

    def build_rows(self) -> list[list[str]]:
        """
        Build data rows for export.

        For objects without expansion, creates one row per object.
        For objects with expansion, creates multiple rows (cartesian product).

        Returns:
            List of rows, where each row is a list of string values
        """
        rows = []

        for obj in self.queryset:
            if self.has_expansion():
                # Multiple rows per object (cartesian product of relations)
                rows.extend(self._build_expanded_rows(obj))
            else:
                # Single row per object
                rows.append(self._build_simple_row(obj))

        return rows

    def _build_simple_row(self, obj: models.Model) -> list[str]:
        """
        Build a single row for an object without expansion.

        Simply extracts and formats each field value in order.
        """
        row = []
        for field_name in self.fields:
            value = self.admin_class.format_export_value(obj, field_name)
            row.append(value)
        return row

    def _build_expanded_rows(self, obj: models.Model) -> list[list[str]]:
        """
        Build multiple rows for an object with expanded relationships.

        Creates a cartesian product of all expanded relationships.
        For example, if an event has 3 attendees and each attendee has 2 groups,
        this generates 6 rows (3 * 2).

        Args:
            obj: The model instance to expand

        Returns:
            List of rows, where each row includes base fields + expanded fields
        """
        # Start with base field values (non-expanded, non-count)
        base_values = []
        for field in self.base_fields:
            if not field.endswith(EXPORT_COUNT_SUFFIX):
                base_values.append(self.admin_class.format_export_value(obj, field))

        # Generate expanded data (all combinations)
        expanded_data = self._generate_expanded_combinations(obj)

        # Combine base + expanded for each row
        rows = []
        for expanded_row in expanded_data:
            row = base_values.copy()
            row.extend(expanded_row)
            rows.append(row)

        # If no expanded data (empty relationships), return single row with base values
        return rows if rows else [base_values]

    def _generate_expanded_combinations(self, obj: models.Model) -> list[list[str]]:
        """
        Generate all combinations of expanded field values using recursive expansion.

        This is the core algorithm for handling nested M2M and 1-to-many relationships.
        It creates a cartesian product at each level of nesting.

        Args:
            obj: The model instance to expand

        Returns:
            List of rows, where each row contains only the expanded field values
            (base fields are added by the caller)
        """
        # Build tree structure from expanded field paths
        expansion_structure = self._build_expansion_structure()

        # Generate all combinations recursively
        result = self._expand_recursively(obj, expansion_structure, self.base_fields)

        return result if result else [[]]

    def _build_expansion_structure(self) -> dict:
        """
        Build a tree structure from expanded field paths.

        Converts flat list of paths like:
        - 'attendees__email'
        - 'attendees__first_name'
        - 'attendees__groups__name'

        Into nested structure:
        {
            'attendees': {
                'fields': [('attendees__email', 'email'), ('attendees__first_name', 'first_name')],
                'nested': {
                    'groups': {
                        'fields': [('attendees__groups__name', 'name')],
                        'nested': {}
                    }
                }
            }
        }

        Returns:
            Nested dict where keys are relation names and values contain
            'fields' (list of tuples) and 'nested' (sub-relations dict)
        """
        tree = {}

        for field_path in self.expanded_fields:
            parts = field_path.split(EXPORT_FIELD_SEPARATOR)
            current = tree

            # Navigate/build the tree
            for i, part in enumerate(parts[:-1]):  # All but last are relations
                if part not in current:
                    current[part] = {"fields": [], "nested": {}}

                # If this is the last relation, add the final field
                if i == len(parts) - 2:
                    current[part]["fields"].append((field_path, parts[-1]))
                    break

                # Continue to next level
                current = current[part]["nested"]

        return tree

    def _expand_recursively(  # noqa: PLR0912
        self, current_obj: models.Model, tree_node: dict, base_fields: list[str], prefix: str = ""
    ) -> list[list[str]]:
        """
        Recursively expand relationships and generate all combinations.

        This is the heart of the cartesian product generation. It:
        1. Iterates through each relation at this level
        2. Gets related objects
        3. For each related object, extracts field values
        4. Recursively processes nested relations
        5. Combines everything into a cartesian product

        Args:
            current_obj: Current model instance being expanded
            tree_node: Current node in the expansion tree
            base_fields: All base fields (for finding count fields)
            prefix: Current field path prefix

        Returns:
            List of rows where each row is a list of string values
        """
        if not tree_node:
            return [[]]

        all_rows = [[]]

        for relation_name, relation_config in tree_node.items():
            fields_to_add = relation_config["fields"]
            nested_tree = relation_config["nested"]
            relation_path = f"{prefix}{relation_name}" if prefix else relation_name
            count_field = f"{relation_path}{EXPORT_COUNT_SUFFIX}"

            new_rows = []

            for row in all_rows:
                # Get related objects
                related_manager = getattr(current_obj, relation_name)
                if hasattr(related_manager, "all"):
                    related_objects = list(related_manager.all())
                else:
                    # Single related object (1-to-1 or FK)
                    related_objects = [related_manager] if related_manager else []

                # Handle empty relationships
                if not related_objects:
                    new_row = row.copy()

                    # Add count field if requested
                    if count_field in base_fields:
                        new_row.append("0")

                    # Add empty values for all fields at this level
                    for _ in fields_to_add:
                        new_row.append("")

                    # Add empty values for nested fields
                    if nested_tree:
                        empty_nested = self._get_empty_nested_values(
                            nested_tree, base_fields, f"{relation_path}{EXPORT_FIELD_SEPARATOR}"
                        )
                        new_row.extend(empty_nested)

                    new_rows.append(new_row)
                else:
                    # For each related object, create rows
                    for related_obj in related_objects:
                        new_row = row.copy()

                        # Add count field if requested (same for all rows from this parent)
                        if count_field in base_fields:
                            new_row.append(str(len(related_objects)))

                        # Add field values from this level
                        for _full_field, field_name in fields_to_add:
                            value = getattr(related_obj, field_name, None)
                            if value is not None:
                                if callable(value):
                                    value = value()
                                new_row.append(str(value))
                            else:
                                new_row.append("")

                        # Handle nested expansions recursively
                        if nested_tree:
                            nested_rows = self._expand_recursively(
                                related_obj,
                                nested_tree,
                                base_fields,
                                f"{relation_path}{EXPORT_FIELD_SEPARATOR}",
                            )

                            # Cartesian product with nested rows
                            for nested_row in nested_rows:
                                combined_row = new_row.copy()
                                combined_row.extend(nested_row)
                                new_rows.append(combined_row)
                        else:
                            new_rows.append(new_row)

            all_rows = new_rows

        return all_rows

    def _get_empty_nested_values(
        self, nested_tree: dict, base_fields: list[str], prefix: str
    ) -> list[str]:
        """
        Get empty string values for all fields in a nested tree.

        Used when a relationship is empty to ensure consistent row structure.

        Args:
            nested_tree: The nested expansion structure
            base_fields: All base fields (for finding count fields)
            prefix: Current field path prefix

        Returns:
            List of empty strings matching the expected nested structure
        """
        values = []

        for relation_name, relation_config in nested_tree.items():
            relation_path = f"{prefix}{relation_name}"
            count_field = f"{relation_path}{EXPORT_COUNT_SUFFIX}"

            # Add empty count if requested
            if count_field in base_fields:
                values.append("0")

            # Add empty values for fields at this level
            values.extend([""] * len(relation_config["fields"]))

            # Recursively add empty nested values
            if relation_config["nested"]:
                values.extend(
                    self._get_empty_nested_values(
                        relation_config["nested"],
                        base_fields,
                        f"{relation_path}{EXPORT_FIELD_SEPARATOR}",
                    )
                )

        return values
