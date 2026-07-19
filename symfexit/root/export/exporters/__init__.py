from symfexit.root.export.exporters._abstract_exporter import AbstractExporter
from symfexit.root.export.exporters.csv_exporter import CSVExporter
from symfexit.root.export.exporters.excel_exporter import ExcelExporter
from symfexit.root.export.exporters.json_exporter import JsonExporter

exporters: dict[str, AbstractExporter] = {
    "Excel": ExcelExporter(),
    "CSV": CSVExporter(),
    "JSON": JsonExporter(),
}
