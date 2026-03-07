from django.conf import settings
from django.forms import ClearableFileInput


class _FileValue:
    """Wraps a string path so ClearableFileInput can render it with a URL."""

    def __init__(self, name):
        self.name = name
        self.url = f"{settings.MEDIA_URL}{name}"

    def __str__(self):
        return self.name

    def __bool__(self):
        return bool(self.name)


class ClearableFileInputFromStr(ClearableFileInput):
    template_name = "admin/widgets/clearable_file_input.html"

    def is_initial(self, value):
        return bool(value)

    def format_value(self, value):
        if isinstance(value, str) and value:
            return _FileValue(value)
        return value
