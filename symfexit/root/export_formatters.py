from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from datetime import datetime

from django.http import HttpResponse


class ExportFormatter(ABC):
    """Base class for export formatters following the Strategy pattern."""

    @abstractmethod
    def format(self, headers: list[str], rows: list[list[str]], filename_base: str) -> HttpResponse:
        """
        Format structured data and return an HttpResponse.

        Args:
            headers: List of column header labels
            rows: List of data rows (each row is a list of string values)
            filename_base: Base filename without extension or timestamp

        Returns:
            HttpResponse with properly formatted content and headers
        """
        pass


class CSVFormatter(ExportFormatter):
    """CSV format generator with Excel compatibility."""

    def format(self, headers: list[str], rows: list[list[str]], filename_base: str) -> HttpResponse:
        """Generate CSV file with UTF-8 BOM for Excel compatibility."""
        # Create response with CSV content type
        response = HttpResponse(content_type="text/csv; charset=utf-8")

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_base}_{timestamp}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # Write UTF-8 BOM for Excel compatibility
        # This ensures Excel opens the file with correct encoding
        response.write("\ufeff")

        # Write data
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows(rows)

        return response


class ExcelFormatter(ExportFormatter):
    """Excel (.xlsx) format generator with basic type inference."""

    def format(self, headers: list[str], rows: list[list[str]], filename_base: str) -> HttpResponse:
        """Generate Excel file with styled headers and auto-sized columns."""
        try:
            from openpyxl import Workbook  # noqa: PLC0415
            from openpyxl.styles import Font  # noqa: PLC0415
        except ImportError:
            return HttpResponse(
                "Excel export requires the 'openpyxl' package. "
                "Please install it with: pip install openpyxl",
                status=500,
                content_type="text/plain",
            )

        # Create workbook and worksheet
        workbook = Workbook()
        worksheet = workbook.active

        # Set sheet title (Excel has 31 character limit)
        worksheet.title = filename_base[:31]

        # Write header row
        worksheet.append(headers)

        # Style headers with bold font
        header_font = Font(bold=True)
        for cell in worksheet[1]:
            cell.font = header_font

        # Write data rows
        for row in rows:
            worksheet.append(row)

        # Auto-adjust column widths for readability
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter

            # Find the longest value in this column
            for cell in column:
                try:
                    cell_length = len(str(cell.value))
                    max_length = max(max_length, cell_length)
                except Exception:
                    pass

            # Set width with reasonable limits
            # Add 2 for padding, max out at 50 for very long content
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

        # Save to BytesIO buffer
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        # Create response
        response = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_base}_{timestamp}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response


# Registry of available formatters
FORMATTERS = {
    "csv": CSVFormatter(),
    "excel": ExcelFormatter(),
}


def get_formatter(format_type: str) -> ExportFormatter:
    """Get a formatter instance by type."""
    if format_type not in FORMATTERS:
        raise ValueError(
            f"Unknown export format: {format_type}. "
            f"Available formats: {', '.join(FORMATTERS.keys())}"
        )

    return FORMATTERS[format_type]
