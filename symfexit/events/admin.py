from django.contrib import admin
from symfexit.events.models import Event

# Register your models here.


@admin.register(Event)
class EventsAdmin(admin.ModelAdmin):
    pass
