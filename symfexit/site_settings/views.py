from django import forms
from django.contrib import messages
from django.db import connection
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from symfexit.tenants.admin import ConfigFormMixin


class SiteSettingsForm(ConfigFormMixin, forms.Form):
    """Standalone form (not ModelForm) for the site settings page."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        config_data = tenant.config if tenant else {}
        self._init_config_fields(config_data)

    def save(self):
        self._save_config_fields(self.tenant, self.cleaned_data)
        self.tenant.save(update_fields=["config"])


class SiteSettingsView(FormView):
    template_name = "admin/site_settings/change_list.html"
    form_class = SiteSettingsForm
    admin_site = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = connection.tenant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.admin_site.each_context(self.request))
        tenant = connection.tenant
        context["config_values"] = context["form"].get_config_rows(tenant)
        context["title"] = _("Site settings")
        return context

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Live settings updated successfully."))
        return HttpResponseRedirect(".")

    def form_invalid(self, form):
        messages.error(self.request, _("Failed to update live settings."))
        return super().form_invalid(form)
