from django.forms import ClearableFileInput


class ClearableFileInputFromStr(ClearableFileInput):
    def is_initial(self, value):
        return bool(value)

