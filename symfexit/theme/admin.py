from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from django.urls.resolvers import URLPattern
from django.views.generic import TemplateView

from symfexit.theme.models import TailwindKey
from symfexit.worker.registry import add_task


# class ConfigAdmin(ConstanceAdmin):
#     change_list_template = "admin/constance_theme/change_list.html"
#     # change_list_template = 'admin/constance/includes/results_list.html'

#     def __init__(self, model, admin_site):
#         super().__init__(model, admin_site)
#         self.opts.app_label = "theme"


# admin.site.unregister([Config])
# admin.site.register([Config], ConfigAdmin)


class TailwindAdmin(admin.ModelAdmin):
    change_list_template = "admin/tailwind_keys/change_list.html"
    exclude = ("id",)

    def get_urls(self) -> list[URLPattern]:
        return [
            path("rebuild/", self.rebuild, name="rebuild"),
        ] + super().get_urls()

    def rebuild(self, request):
        return TemplateResponse(request, "admin/rebuild_theme.html", {})


admin.site.register([TailwindKey], TailwindAdmin)


class RebuildTheme(TemplateView):
    template_name = "admin/rebuild_theme/index.html"
    admin_site = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.admin_site.each_context(self.request))
        context["title"] = "Rebuild Theme"
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        context["task_added"] = False
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        task = add_task("rebuild_theme")
        context = self.get_context_data()
        context["task_added"] = True
        context["task_id"] = task.id
        return self.render_to_response(context)
