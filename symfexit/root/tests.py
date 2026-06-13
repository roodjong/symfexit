import json
from datetime import date
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock

from django.core.exceptions import FieldDoesNotExist
from django.test import SimpleTestCase
from django.utils.functional import SimpleLazyObject

from symfexit.root.export.databuilder import ExportDataBuilder
from symfexit.root.export.exporters.json_exporter import JsonExporter


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


class BuildRowsTest(SimpleTestCase):
    def test_primitive_values_pass_through(self):
        obj = make_obj(name="Alice", age=30, score=9.5, active=True)
        model = make_model()
        fields = ["name", "age", "score", "active"]
        builder = ExportDataBuilder(fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], fields), [["Alice", 30, 9.5, True]])

    def test_none_passes_through(self):
        obj = make_obj(note=None)
        model = make_model()
        builder = ExportDataBuilder(["note"], [obj], model)
        self.assertEqual(builder.build_rows([obj], ["note"]), [[None]])

    def test_non_primitive_coerced_to_str(self):
        obj = make_obj(joined=date(2024, 1, 15), balance=Decimal("12.50"))
        model = make_model()
        fields = ["joined", "balance"]
        builder = ExportDataBuilder(fields, [obj], model)
        rows = builder.build_rows([obj], fields)
        self.assertEqual(rows, [["2024-01-15", "12.50"]])

    def test_tuple_field_reads_correct_attribute(self):
        obj = make_obj(internal="value")
        model = make_model()
        fields = [("internal", "Label")]
        builder = ExportDataBuilder(fields, [obj], model)
        self.assertEqual(builder.build_rows([obj], fields), [["value"]])


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
