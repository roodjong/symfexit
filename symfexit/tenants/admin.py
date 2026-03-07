from django import forms
from django.apps import apps
from django.conf import settings
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
from symfexit.tenants.models import Client, Domain


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


IMAGE_FIELD_KEYS = {
    key
    for key, meta in settings.CONSTANCE_CONFIG.items()
    if len(meta) > 2 and meta[2] == "image_field"  # noqa: PLR2004
}


def _make_config_model_form():
    """Build a ModelForm class with fields for each CONSTANCE_CONFIG key."""
    field_defs = _make_config_fields()

    class ClientConfigForm(forms.ModelForm):
        class Meta:
            model = Client
            fields = ("name",)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instance = kwargs.get("instance")
            config_data = instance.config if instance and instance.pk else {}
            for cfg_key, cfg_meta in settings.CONSTANCE_CONFIG.items():
                form_key = f"config_{cfg_key}"
                if form_key in self.fields:
                    self.fields[form_key].initial = config_data.get(cfg_key, cfg_meta[0])

        def save(self, commit=True):
            instance = super().save(commit=False)
            _save_config_fields(instance, self.cleaned_data)
            if commit:
                instance.save()
            return instance

        def get_config_rows(self):
            """Return config data for the template table."""
            return _get_config_rows(self.instance, self)

    for fname, fobj in field_defs.items():
        ClientConfigForm.base_fields[fname] = fobj
        ClientConfigForm.declared_fields[fname] = fobj

    return ClientConfigForm


def _make_config_fields():
    """Create form field definitions for all CONSTANCE_CONFIG keys."""
    field_defs = {}
    for key, meta in settings.CONSTANCE_CONFIG.items():
        default = meta[0]
        label = str(meta[1])
        field_type = meta[2] if len(meta) > 2 else None
        if field_type == "image_field":
            field_defs[f"config_{key}"] = forms.FileField(
                label=label, required=False, widget=ClearableFileInputFromStr
            )
        elif isinstance(default, bool):
            field_defs[f"config_{key}"] = forms.BooleanField(label=label, required=False)
        elif isinstance(default, int):
            field_defs[f"config_{key}"] = forms.IntegerField(label=label, required=False)
        else:
            field_defs[f"config_{key}"] = forms.CharField(
                label=label, required=False, widget=forms.Textarea(attrs={"rows": 3})
            )
    return field_defs


def _save_config_fields(client, cleaned_data):
    """Save config fields from cleaned form data into client.config."""
    if client.config is None:
        client.config = {}
    for cfg_key, cfg_meta in settings.CONSTANCE_CONFIG.items():
        form_key = f"config_{cfg_key}"
        if form_key not in cleaned_data:
            continue
        value = cleaned_data[form_key]
        if cfg_key in IMAGE_FIELD_KEYS:
            if value is False:
                client.config[cfg_key] = ""
            elif value:
                name = default_storage.save(value.name, value)
                client.config[cfg_key] = name
        else:
            default = cfg_meta[0]
            if isinstance(default, int) and value is None:
                value = default
            client.config[cfg_key] = value


def _get_config_rows(instance, form):
    """Return config row data for the template table."""
    config_data = instance.config if instance and instance.pk else {}
    rows = []
    for cfg_key, cfg_meta in settings.CONSTANCE_CONFIG.items():
        default = cfg_meta[0]
        is_file = cfg_key in IMAGE_FIELD_KEYS
        current = config_data.get(cfg_key, default)
        modified = cfg_key in config_data and config_data[cfg_key] != default
        rows.append(
            {
                "key": cfg_key,
                "description": str(cfg_meta[1]),
                "default": "" if is_file else localize(default),
                "value": localize(current),
                "is_modified": modified,
                "is_file": is_file,
                "is_checkbox": isinstance(default, bool),
                "form_field": form[f"config_{cfg_key}"],
            }
        )
    return rows


ClientConfigForm = _make_config_model_form()


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


class SiteSettingsForm(forms.Form):
    """Standalone form (not ModelForm) for the constance-style settings page."""

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        config_data = tenant.config if tenant else {}
        for key, field in _make_config_fields().items():
            cfg_key = key.removeprefix("config_")
            default = settings.CONSTANCE_CONFIG[cfg_key][0]
            field.initial = config_data.get(cfg_key, default)
            self.fields[key] = field

    def save(self):
        _save_config_fields(self.tenant, self.cleaned_data)
        self.tenant.save(update_fields=["config"])


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
            "config_values": _get_config_rows(tenant, form),
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


admin.site.register([SiteSettings], SiteSettingsAdmin)
