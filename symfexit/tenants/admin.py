from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin.options import csrf_protect_m
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import connection
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.formats import localize
from django.utils.translation import gettext_lazy as _
from django_tenants.admin import TenantAdminMixin

from symfexit.root.helpers import ClearableFileInputFromStr
from symfexit.tenants.adminsite import global_admin
from symfexit.tenants.config import CONFIG_SCHEMA
from symfexit.tenants.models import Client, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


class ConfigFormMixin:
    """Mixin that initialises and saves config fields backed by CONFIG_SCHEMA."""

    def _init_config_fields(self, config_data):
        for key, schema in CONFIG_SCHEMA.items():
            form_key = f"config_{key}"
            if schema.field_type == "image_field":
                form_field = forms.FileField(
                    label=schema.label, required=False, widget=ClearableFileInputFromStr
                )
            elif isinstance(schema.default, bool):
                form_field = forms.BooleanField(label=schema.label, required=False)
            elif isinstance(schema.default, int):
                form_field = forms.IntegerField(label=schema.label, required=False)
            else:
                form_field = forms.CharField(
                    label=schema.label,
                    required=False,
                    widget=forms.Textarea(attrs={"rows": 3}),
                )
            form_field.initial = config_data.get(key, schema.default)
            self.fields[form_key] = form_field

    def _save_config_fields(self, client, cleaned_data):
        if client.config is None:
            client.config = {}
        for key, schema in CONFIG_SCHEMA.items():
            form_key = f"config_{key}"
            if form_key not in cleaned_data:
                continue
            value = cleaned_data[form_key]
            if schema.field_type == "image_field":
                if value is False:
                    client.config[key] = ""
                elif value:
                    name = default_storage.save(value.name, value)
                    client.config[key] = name
            else:
                if isinstance(schema.default, int) and value is None:
                    value = schema.default
                client.config[key] = value

    def get_config_rows(self, instance):
        config_data = instance.config if instance and instance.pk else {}
        rows = []
        for key, schema in CONFIG_SCHEMA.items():
            is_file = schema.field_type == "image_field"
            current = config_data.get(key, schema.default)
            modified = key in config_data and config_data[key] != schema.default
            rows.append(
                {
                    "key": key,
                    "description": str(schema.label),
                    "default": "" if is_file else localize(schema.default),
                    "value": localize(current),
                    "is_modified": modified,
                    "is_file": is_file,
                    "is_checkbox": isinstance(schema.default, bool),
                    "form_field": self[f"config_{key}"],
                }
            )
        return rows


class ClientConfigForm(ConfigFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = ("name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance")
        config_data = instance.config if instance and instance.pk else {}
        self._init_config_fields(config_data)

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._save_config_fields(instance, self.cleaned_data)
        if commit:
            instance.save()
        return instance

    def get_config_rows(self):
        return super().get_config_rows(self.instance)


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


@admin.register(Client, site=global_admin)
class GlobalClientAdmin(TenantAdminMixin, admin.ModelAdmin):
    form = ClientConfigForm
    list_display = ("name",)
    inlines = (DomainInline,)
    change_form_template = "admin/tenants/client/change_form.html"

    def get_fieldsets(self, request, obj=None):
        return [
            (None, {"fields": ("name",)}),
        ]


class SiteSettings:
    """Fake model class for the per-tenant settings admin (like constance's Config)."""

    class Meta:
        app_label = "site_settings"
        object_name = "SiteSettings"
        concrete_model = None
        model_name = module_name = "sitesettings"
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")
        abstract = False
        swapped = False
        is_composite_pk = False

        def get_ordered_objects(self):
            return False

        def get_change_permission(self):
            return f"change_{self.model_name}"

        @property
        def app_config(self):
            return apps.get_app_config(self.app_label)

        @property
        def label(self):
            return f"{self.app_label}.{self.object_name}"

        @property
        def label_lower(self):
            return f"{self.app_label}.{self.model_name}"

    _meta = Meta()


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    change_list_template = "admin/tenants/sitesettings/change_list.html"

    def __init__(self, model, admin_site):
        model._meta.concrete_model = SiteSettings
        super().__init__(model, admin_site)

    def get_urls(self):
        info = f"{self.model._meta.app_label}_{self.model._meta.module_name}"
        return [
            path("", self.admin_site.admin_view(self.changelist_view), name=f"{info}_changelist"),
            path("", self.admin_site.admin_view(self.changelist_view), name=f"{info}_add"),
        ]

    @csrf_protect_m
    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        tenant = connection.tenant
        form = SiteSettingsForm(tenant=tenant)

        if request.method == "POST":
            form = SiteSettingsForm(data=request.POST, files=request.FILES, tenant=tenant)
            if form.is_valid():
                form.save()
                messages.add_message(
                    request, messages.SUCCESS, _("Live settings updated successfully.")
                )
                return HttpResponseRedirect(".")
            messages.add_message(request, messages.ERROR, _("Failed to update live settings."))

        context = {
            **self.admin_site.each_context(request),
            **(extra_context or {}),
            "config_values": form.get_config_rows(tenant),
            "title": _("Site settings"),
            "app_label": "tenants",
            "opts": self.model._meta,
            "form": form,
            "media": self.media + form.media,
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, self.change_list_template, context)

    def has_add_permission(self, *args, **kwargs):
        return False

    def has_delete_permission(self, *args, **kwargs):
        return False
