from django.contrib import admin

from membership.models import Membership

# Register your models here.
@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    pass
