import json
from datetime import date
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock

from django.core.exceptions import FieldDoesNotExist
from django.db import models as django_models
from django.db.models import Manager
from django.test import SimpleTestCase
from django.utils.functional import SimpleLazyObject

from symfexit.root.export.databuilder import ExportDataBuilder
from symfexit.root.export.exporters.json_exporter import JsonExporter
from symfexit.root.export.field_selection import nodes_to_export_fields
from symfexit.root.export.types import fields


def make_model(field_name=None, verbose_name=None):
    """Return a mock model. spec=['_meta'] ensures hasattr returns False for unknown attributes."""
    model = MagicMock(spec=["_meta"])
    if field_name and verbose_name:
        field_mock = MagicMock()
        field_mock.verbose_name = verbose_name
        model._meta.get_field.return_value = field_mock
    else:
        model._meta.get_field.side_effect = FieldDoesNotExist
    return model


def make_obj(**attrs):
    obj = MagicMock(spec=list(attrs.keys()))
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def make_manager(*objects):
    manager = MagicMock(spec=Manager)
    manager.all.return_value = list(objects)
    return manager


class BuildHeaderTest(SimpleTestCase):
    def test_string_field_uses_verbose_name(self):
        model = make_model(field_name="first_name", verbose_name="First Name")
        builder = ExportDataBuilder(["first_name"], [], model)
        self.assertEqual(builder.build_header(model, ["first_name"]), ["First Name"])

    def test_string_field_falls_back_to_title(self):
        model = make_model()
        builder = ExportDataBuilder(["date_of_birth"], [], model)
        self.assertEqual(builder.build_header(model, ["date_of_birth"]), ["Date Of Birth"])

    def test_tuple_field_uses_custom_label(self):
        model = make_model()
        builder = ExportDataBuilder([("internal_name", "Display Name")], [], model)
        self.assertEqual(
            builder.build_header(model, [("internal_name", "Display Name")]),
            ["Display Name"],
        )

    def test_tuple_label_lazy_string_coerced_to_str(self):
        model = make_model()
        lazy_label = cast(str, SimpleLazyObject(lambda: "Name"))
        builder = ExportDataBuilder([("name", lazy_label)], [], model)
        header = builder.build_header(model, [("name", lazy_label)])
        self.assertIsInstance(header[0], str)

    def test_to_one_relationship_generates_nested_headers(self):
        related_model = MagicMock(spec=["_meta"])
        street_field = MagicMock()
        street_field.verbose_name = "Street name"
        city_field = MagicMock()
        city_field.verbose_name = "City"
        related_model._meta.get_field.side_effect = lambda name: {
            "street": street_field,
            "city": city_field,
        }[name]

        parent_model = MagicMock(spec=["_meta"])
        relation_field = MagicMock()
        relation_field.verbose_name = "address"
        relation_field.related_model = related_model
        parent_model._meta.get_field.return_value = relation_field

        parent = cast(type[django_models.Model], parent_model)
        export_fields: fields = [("address", ["street", "city"])]
        builder = ExportDataBuilder(export_fields, [], parent)
        self.assertEqual(
            builder.build_header(parent, export_fields), ["Address Street name", "Address City"]
        )

    def test_to_one_nested_field_label_overrides_verbose_name(self):
        related_model = MagicMock(spec=["_meta"])
        city_field = MagicMock()
        city_field.verbose_name = "City"
        related_model._meta.get_field.side_effect = lambda name: {"city": city_field}[name]

        parent_model = MagicMock(spec=["_meta"])
        relation_field = MagicMock()
        relation_field.verbose_name = "address"
        relation_field.related_model = related_model
        parent_model._meta.get_field.return_value = relation_field

        parent = cast(type[django_models.Model], parent_model)
        export_fields: fields = [("address", [("street", "Home street"), "city"])]
        builder = ExportDataBuilder(export_fields, [], parent)
        self.assertEqual(
            builder.build_header(parent, export_fields), ["Address Home street", "Address City"]
        )


class BuildRowsTest(SimpleTestCase):
    def test_primitive_values_pass_through(self):
        obj = make_obj(name="Alice", age=30, score=9.5, active=True)
        model = make_model()
        export_fields: fields = ["name", "age", "score", "active"]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [["Alice", 30, 9.5, True]])

    def test_none_passes_through(self):
        obj = make_obj(note=None)
        model = make_model()
        builder = ExportDataBuilder(["note"], [obj], model)
        self.assertEqual(builder.build_rows([obj], ["note"]), [[None]])

    def test_non_primitive_coerced_to_str(self):
        obj = make_obj(joined=date(2024, 1, 15), balance=Decimal("12.50"))
        model = make_model()
        export_fields: fields = ["joined", "balance"]
        builder = ExportDataBuilder(export_fields, [obj], model)
        rows = builder.build_rows([obj], export_fields)
        self.assertEqual(rows, [["2024-01-15", "12.50"]])

    def test_tuple_field_reads_correct_attribute(self):
        obj = make_obj(internal="value")
        model = make_model()
        export_fields: fields = [("internal", "Label")]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [["value"]])

    def test_nested_model_field_flattened_into_row(self):
        address = make_obj(street="Main St", city="Amsterdam")
        obj = make_obj(address=address)
        model = make_model()
        sub_fields: fields = ["street", "city"]
        export_fields: fields = [("address", sub_fields)]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [["Main St", "Amsterdam"]])

    def test_null_to_one_relationship_produces_none_values(self):
        obj = make_obj(address=None)
        model = make_model()
        sub_fields: fields = ["street", "city"]
        export_fields: fields = [("address", sub_fields)]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [[None, None]])

    def test_chained_to_one_with_null_middle_produces_none_for_all_nested_fields(self):
        # A → B → C, B is None: C's fields must still appear as None so the row length matches the header
        obj = make_obj(b=None)
        model = make_model()
        export_fields: fields = [("b", [("c", ["attr1", "attr2"])])]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [[None, None]])

    def test_chained_to_many_with_empty_middle_produces_none_for_all_nested_fields(self):
        # A → (many) B (empty) → (many) C: C's fields must still appear as None so the row length matches the header
        obj = make_obj(bs=make_manager())
        model = make_model()
        export_fields: fields = [("bs", [("cs", ["attr1", "attr2"])])]
        builder = ExportDataBuilder(export_fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], export_fields), [[None, None]])


class FieldSelectionTest(SimpleTestCase):
    def test_unselected_fields_are_excluded(self):
        export_fields: fields = ["name", "email", "age"]
        self.assertEqual(nodes_to_export_fields(export_fields, ["name", "age"]), ["name", "age"])

    def test_custom_label_is_preserved(self):
        export_fields: fields = [("internal_name", "Display Name"), "email"]
        result = nodes_to_export_fields(export_fields, ["internal_name"])
        self.assertEqual(result, [("internal_name", "Display Name")])

    def test_nested_relation_is_filtered(self):
        export_fields: fields = [("address", ["street", "city", "country"])]
        result = nodes_to_export_fields(export_fields, ["address.street", "address.city"])
        self.assertEqual(result, [("address", ["street", "city"])])

    def test_relation_excluded_when_no_sub_fields_selected(self):
        export_fields: fields = ["name", ("address", ["street", "city"])]
        result = nodes_to_export_fields(export_fields, ["name"])
        self.assertEqual(result, ["name"])

    def test_nested_custom_label_is_preserved(self):
        # This is the critical case: a custom label inside a relation must survive the round-trip
        export_fields: fields = [("address", [("street", "Home street"), "city"])]
        result = nodes_to_export_fields(export_fields, ["address.street"])
        self.assertEqual(result, [("address", [("street", "Home street")])])


class JsonExporterTest(SimpleTestCase):
    def test_returns_json_response_with_correct_data(self):
        exporter = JsonExporter()
        response = exporter.export(["name", "age"], [["Alice", 30], ["Bob", 25]], "test")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data, [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}])

    def test_sets_content_disposition(self):
        exporter = JsonExporter()
        response = exporter.export(["x"], [[1]], "export")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="export.json"')

    def test_empty_queryset(self):
        exporter = JsonExporter()
        response = exporter.export(["name"], [], "empty")
        self.assertEqual(json.loads(response.content), [])
