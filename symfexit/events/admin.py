from django.contrib import admin
from django.utils.html import format_html

from symfexit.events.models import Event

# Register your models here.


@admin.register(Event)
class EventsAdmin(admin.ModelAdmin):
    readonly_fields = ("attendees_display",)
    list_display = ("event_name", "event_date", "event_organiser")

    def attendees_display(self, obj):
        attendees = obj.attendees.all().order_by("email")
        if attendees.exists():
            # Wrap each attendee in <li> and all in <ul>
            items = "".join(f"<li>{user}</li>" for user in attendees)
            return format_html(f'<ul style="margin:unset; padding: unset;">{items}</ul>')
        return "-"

    attendees_display.short_description = "Attendees"
