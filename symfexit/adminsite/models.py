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
        on_delete=models.CASCADE,
        related_name="well_known_code",
    )

    def __str__(self):
        return self.code

    @classmethod
    def get_or_create(cls, code):
        try:
            well_known = WellKnownPermissionGroup.objects.get(code=code.value)
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
        return well_known

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


class GroupFlags(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="flags",
    )
    members_become_staff = models.BooleanField(
        help_text="Designates whether members of this group can log in to the administration"
    )

    def __str__(self):
        return f"Flags for group {self.group}"
