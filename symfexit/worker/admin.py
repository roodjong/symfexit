from django.contrib import admin

from symfexit.tenants.adminsite import global_admin
from symfexit.worker.models import Task

# Register your models here.


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    fields = ("name", "status", "output", "created_at", "picked_up_at", "completed_at")
    readonly_fields = (
        "output",
        "created_at",
    )

    def get_queryset(self, request):
        tenant = request.tenant
        return super().get_queryset(request).filter(tenant=tenant)


@admin.register(Task, site=global_admin)
class GlobalTaskAdmin(admin.ModelAdmin):
    fields = ("name", "status", "output", "created_at", "picked_up_at", "completed_at")
    readonly_fields = (
        "output",
        "created_at",
    )
