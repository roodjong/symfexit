from symfexit.root.export.exporters._abstract_exporter import AbstractExporter
from symfexit.root.export.exporters.json_exporter import JsonExporter

exporters: dict[str, AbstractExporter] = {
    "JSON": JsonExporter(),
}
