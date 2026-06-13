from django.http import HttpResponse, JsonResponse

from symfexit.root.export.exporters._abstract_exporter import AbstractExporter


class JsonExporter(AbstractExporter):
    """Exporter that converts data to JSON format and returns it as an HTTP response."""

    def export(
        self, header: list[str], rows: list[list[str | int | float | bool | None]], filename: str
    ) -> HttpResponse:
        # create dict of data
        data = [dict(zip(header, row, strict=False)) for row in rows]

        # create response
        response = JsonResponse(data, safe=False)
        response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
        return response
