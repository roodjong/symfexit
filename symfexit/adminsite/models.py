from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, models, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


class WellKnownPermissionGroup(models.Model):
    class WellKnownPermissionGroups(models.TextChoices):
        VIEW_ALL = "view_all", _("View all")
        CONTACT_PERSON = "contact_person", "Contact person"
        BOARD = "board", _("Board")

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

    class Meta:
        verbose_name = _("well known permission group")
        verbose_name_plural = _("well known permission groups")

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
        # get or create flags
        try:
            flags = self.group.flags
        except GroupFlags.DoesNotExist:
            flags = GroupFlags(group=self.group)

        # reset the flags to default value
        flags.members_become_staff = False

        # Set permissions on group
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
                flags.members_become_staff = True
            case WellKnownPermissionGroup.WellKnownPermissionGroups.BOARD:
                self.group.permissions.set(
                    [
                        Permission.objects.get(codename="add_membership"),
                        Permission.objects.get(codename="view_membership"),
                        Permission.objects.get(codename="add_localgroup"),
                        Permission.objects.get(codename="change_localgroup"),
                        Permission.objects.get(codename="delete_localgroup"),
                        Permission.objects.get(codename="view_localgroup"),
                        Permission.objects.get(codename="add_member"),
                        Permission.objects.get(codename="change_member"),
                        Permission.objects.get(codename="delete_member"),
                        Permission.objects.get(codename="view_member"),
                        Permission.objects.get(codename="add_supportmember"),
                        Permission.objects.get(codename="change_supportmember"),
                        Permission.objects.get(codename="delete_supportmember"),
                        Permission.objects.get(codename="view_supportmember"),
                        Permission.objects.get(codename="add_membershipapplication"),
                        Permission.objects.get(codename="change_membershipapplication"),
                        Permission.objects.get(codename="delete_membershipapplication"),
                        Permission.objects.get(codename="view_membershipapplication"),
                    ]
                )
                flags.members_become_staff = True
            case WellKnownPermissionGroup.WellKnownPermissionGroups.CONTACT_PERSON:
                self.group.permissions.set(
                    [
                        Permission.objects.get(codename="view_membership"),
                        Permission.objects.get(codename="view_member"),
                        Permission.objects.get(codename="change_member"),
                    ]
                )
                flags.members_become_staff = True
        # save the flags
        flags.save()


class GroupFlags(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="flags",
    )

    members_become_staff = models.BooleanField(
        _("Members become staff"),
        help_text=_("Designates whether members of this group can log in to the administration"),
    )

    class Meta:
        verbose_name = _("group flags")

    def __str__(self):
        return f"Flags for group {self.group}"


def reset_user_staff(group: Group):
    for user in group.user_set.all():
        user.set_staff_rights()
        user.save()


@receiver(post_save, sender=GroupFlags)
@receiver(post_delete, sender=GroupFlags)
def on_group_change(sender, instance: GroupFlags, **kwargs):
    transaction.on_commit(lambda: reset_user_staff(instance.group))
