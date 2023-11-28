from django.apps import AppConfig


class HomeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "home"

    def menu_items(self):
        return [{"name": "Home", "viewname": "home:home", "order": 0}]
