from django.contrib import admin

from symfexit.worker.models import Task

# Register your models here.


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    fields = ("name", "status", "output", "created_at", "picked_up_at", "completed_at")
    readonly_fields = (
        "output",
        "created_at",
    )
