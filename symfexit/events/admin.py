from django.contrib import admin
from django.utils.html import format_html

from symfexit.events.models import Event
from symfexit.members.admin import UserAdmin
from symfexit.root.export_mixin import ExportMixin


@admin.register(Event)
class EventsAdmin(ExportMixin, admin.ModelAdmin):
    readonly_fields = ("attendees_display",)
    list_display = ("event_name", "event_date", "event_end", "event_organiser")

    # Export configuration
    export_fields = [
        "event_name",
        "event_date",
        "event_end",
        "event_organiser",
        "event_desc",
        "attendees",
    ]

    # Configure attendees (M2M) to use UserAdmin's export config
    export_model_config = [
        ("attendees", UserAdmin),
    ]

    def get_export_queryset(self, request, ids):
        """Optimize queryset for export by prefetching related data."""
        queryset = super().get_export_queryset(request, ids)
        return queryset.prefetch_related("attendees__groups")

    def attendees_display(self, obj):
        attendees = obj.attendees.all().order_by("email")
        if attendees.exists():
            # Wrap each attendee in <li> and all in <ul>
            items = "".join(f"<li>{user}</li>" for user in attendees)
            return format_html('<ul style="margin:unset; padding: unset;">{}</ul>', items)
        return "-"

    attendees_display.short_description = "Attendees"
