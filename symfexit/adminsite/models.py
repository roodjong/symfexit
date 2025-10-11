from django.contrib.auth.models import Group
from django.db import IntegrityError, models


def get_or_create(code):
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
        well_known.save()
    return group

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