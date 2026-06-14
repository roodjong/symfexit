import csv
from io import StringIO

from django.http import HttpResponse

from symfexit.root.export.exporters._abstract_exporter import AbstractExporter


class CSVExporter(AbstractExporter):
    """Exporter that converts data to CSV format and returns it as an HTTP response."""

    def export(
        self, header: list[str], rows: list[list[str | int | float | bool | None]], filename: str
    ) -> HttpResponse:
        # create CSV data
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(rows)

        # create response
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return response
