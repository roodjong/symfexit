import io

from django.http import HttpResponse
from openpyxl import Workbook

from symfexit.root.export.exporters._abstract_exporter import AbstractExporter


class ExcelExporter(AbstractExporter):
    """Exporter that converts data to Excel (.xlsx) format and returns it as an HTTP response."""

    def export(
        self, header: list[str], rows: list[list[str | int | float | bool | None]], filename: str
    ) -> HttpResponse:
        wb = Workbook()
        ws = wb.active
        ws.append(header)
        for row in rows:
            ws.append(row)

        output = io.BytesIO()
        wb.save(output)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response
