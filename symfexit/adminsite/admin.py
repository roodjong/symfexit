from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
from .models import GroupFlags

admin.site.unregister(Group)


class GroupFlagsInline(admin.StackedInline):
    model = GroupFlags


@admin.register(Group)
class ExtendedGroupAdmin(GroupAdmin):
    inlines = [GroupFlagsInline]
