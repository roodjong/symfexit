from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "members"

    def menu_items(self):
        return [
            {"name": "Gegevens", "viewname": "members:memberdata", "order": 1},
            {"name": "Uitloggen", "viewname": "members:logout", "order": 3},
        ]
