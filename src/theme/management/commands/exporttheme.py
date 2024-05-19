import json

from django.core.management import BaseCommand

from theme.models import TailwindKey


class Command(BaseCommand):
    help = "Export theme keys"

    def handle(self, *args, **options):
        try:
            primary_value = TailwindKey.objects.get(name="primary").value
        except TailwindKey.DoesNotExist:
            primary_value = "#C2000B"

        self.stdout.write(
            json.dumps(
                {
                    "primary": primary_value,
                }
            )
        )
