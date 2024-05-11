from constance import config
from django.contrib import admin

from home.models import HomePage


@admin.register(HomePage)
class HomePageAdmin(admin.ModelAdmin):
    def change_view(self, request, object_id, form_url=""):
        obj = HomePage.objects.filter(id=object_id)[0]
        if config.HOMEPAGE_CURRENT == obj.pk:
            return super().change_view(
                request,
                object_id,
                form_url,
                {
                    "homepage": obj,
                    "show_save_and_add_another": False,
                    "title": "Change current homepage",
                },
            )
        return super().change_view(
            request,
            object_id,
            form_url,
            {
                "homepage": obj,
                "show_save_and_add_another": False,
                "title": "Build new homepage",
                "show_save_and_set": True,
            },
        )

    def response_change(self, request, obj):
        if "_setcurrent" in request.POST:
            config.HOMEPAGE_CURRENT = obj.pk
            self.message_user(request, "This is now the current homepage.")
            request.POST = request.POST.copy()
            request.POST["_continue"] = True
            return super().response_change(request, obj)
        return super().response_change(request, obj)
