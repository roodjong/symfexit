from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, models


class WellKnownPermissionGroup(models.Model):
    class WellKnownPermissionGroups(models.TextChoices):
        VIEW_ALL = "view_all", "View all"

    code = models.CharField(
        unique=True,
        max_length=255,
        choices=WellKnownPermissionGroups.choices,
    )

    group = models.OneToOneField(
        Group,
        on_delete=models.PROTECT,
        related_name="well_known_code",
    )

    def __str__(self):
        return self.code

    @classmethod
    def get_or_create(cls, code):
        try:
            group = WellKnownPermissionGroup.objects.get(code=code.value)
        except WellKnownPermissionGroup.DoesNotExist:
            name = code.label
            group = None
            while group is None:
                try:
                    group = Group.objects.create(name=name)
                except IntegrityError:
                    name = name + " (well known)"
            well_known = WellKnownPermissionGroup(code=code.value, group=group)
            well_known.update_permissions()
            well_known.save()
        return group

    def update_permissions(self):
        match self.code:
            case WellKnownPermissionGroup.WellKnownPermissionGroups.VIEW_ALL.value:
                self.group.permissions.set(
                    [
                        Permission.objects.get(codename="view_localgroup"),
                        Permission.objects.get(codename="view_member"),
                        Permission.objects.get(codename="view_supportmember"),
                        Permission.objects.get(codename="view_user"),
                        Permission.objects.get(codename="view_membershipapplication"),
                    ]
                )
