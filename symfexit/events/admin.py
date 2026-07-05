from django.contrib import admin
from django.utils.html import format_html, format_html_join

from symfexit.events.models import Event


@admin.register(Event)
class EventsAdmin(admin.ModelAdmin):
    readonly_fields = ("attendees_display",)
    list_display = ("event_name", "event_date", "event_end", "event_organiser")

    def attendees_display(self, obj):
        attendees = obj.attendees.all().order_by("email")
        if attendees.exists():
            # Wrap each attendee in <li> and all in <ul>
            user_list = format_html_join(
                "\n",
                "<li>{}</li>",
                ((user.get_full_name(),) for user in attendees),
            )
            return user_list

            return (
                format_html('<ul style="margin:unset; padding: unset;">')
                + user_list
                + format_html("</ul>")
            )

        return "-"

    attendees_display.short_description = "Attendees"
