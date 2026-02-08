from django.contrib import admin
from symfexit.payments.mollie.models import MollieSettings


class MollieSettingsInline(admin.StackedInline):
    model = MollieSettings
    extra = 0
    max_num = 1
