from django.contrib import admin

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.membership.forms import PaymentTier, PaymentTierInfo
from symfexit.membership.models import MembershipTier, MembershipType
from symfexit.payments.models import Order
from symfexit.tenants.config import config


class MembershipTierInline(admin.TabularInline):
    model = MembershipTier
    extra = 1
    autocomplete_fields = ("product",)


@admin.register(MembershipType)
class MembershipTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "position")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("custom_amount_product",)
    inlines = [MembershipTierInline]
