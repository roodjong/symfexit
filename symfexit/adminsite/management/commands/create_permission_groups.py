from django.contrib.auth.models import Group, Permission
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "Creates and updates default permission groups"

    def handle(self, *args, **options):
        view_all_group, created = Group.objects.get_or_create(name="View all")
        all_view_permissions = Permission.objects.filter(codename__startswith="view")
        view_all_group.permissions.set(all_view_permissions)
