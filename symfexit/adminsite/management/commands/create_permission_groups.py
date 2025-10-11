from django.core.management import BaseCommand

from symfexit.adminsite.models import WellKnownPermissionGroup


class Command(BaseCommand):
    help = "Creates and updates default permission groups"

    def handle(self, *args, **options):
        group_ref = WellKnownPermissionGroup.get_or_create(
            code=WellKnownPermissionGroup.WellKnownPermissionGroups.VIEW_ALL
        )
        group_ref.update_permissions()
