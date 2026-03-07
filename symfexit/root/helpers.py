from django.forms import ClearableFileInput


class ClearableFileInputFromStr(ClearableFileInput):
    template_name = "admin/widgets/clearable_file_input.html"

    def is_initial(self, value):
        return bool(value)
