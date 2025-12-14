from django.core.management import BaseCommand

from symfexit.adminsite.models import WellKnownPermissionGroup


class Command(BaseCommand):
    help = "Creates and updates default permission groups"

    def handle(self, *args, **options):
        groups = [
            WellKnownPermissionGroup.WellKnownPermissionGroups.VIEW_ALL,
            WellKnownPermissionGroup.WellKnownPermissionGroups.BOARD,
            WellKnownPermissionGroup.WellKnownPermissionGroups.CONTACT_PERSON,
        ]
        for code in groups:
            group_ref = WellKnownPermissionGroup.get_or_create(code=code)
            group_ref.update_permissions()
