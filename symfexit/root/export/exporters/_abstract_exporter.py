from abc import ABC, abstractmethod

from django.http import HttpResponse


class AbstractExporter(ABC):
    """Abstract base class for data exporters."""

    @abstractmethod
    def export(
        self, header: list[str], rows: list[list[str | int | float | bool | None]], filename: str
    ) -> HttpResponse:
        pass
