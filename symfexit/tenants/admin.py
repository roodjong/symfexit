from django import forms
from django.contrib import admin
from django.core.files.storage import default_storage
from django.utils.formats import localize
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
