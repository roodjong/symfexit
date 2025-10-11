from django.contrib.auth.models import Permission
from django.core.management import BaseCommand

from symfexit.adminsite.models import WellKnownPermissionGroup, get_or_create


class Command(BaseCommand):
    help = "Creates and updates default permission groups"

    def handle(self, *args, **options):
        view_all_group_ref = get_or_create(
            code=WellKnownPermissionGroup.WellKnownPermissionGroups.VIEW_ALL
        )
        view_all_group = view_all_group_ref.group
        all_view_permissions = Permission.objects.filter(codename__startswith="view")
        view_all_group.permissions.set(all_view_permissions)
