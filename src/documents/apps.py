from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"

    def menu_items(self):
        return [{"name": "Documenten", "viewname": "documents:documents", "order": 2}]
