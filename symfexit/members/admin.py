from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.filters import SimpleListFilter
from django.contrib.admin.options import IS_POPUP_VAR, csrf_protect_m
from django.contrib.admin.utils import unquote
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.admin import sensitive_post_parameters_m
from django.contrib.auth.forms import (
    AdminPasswordChangeForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import router, transaction
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from symfexit.members.models import LocalGroup, User, generate_member_number

Group._meta.verbose_name = _("Permission Group")
Group._meta.verbose_name_plural = _("Permission Groups")

# class MembershipInline(admin.StackedInline):
#     model = Membership
#     extra = 0

#     # autocomplete_fields = ("address",)
#     exclude = ()


class IsActiveFilter(SimpleListFilter):
    title = _("is registered")
    parameter_name = "is_active"

    def lookups(self, request, model_admin):
        return [(None, _("Yes")), ("N", _("No")), ("A", _("All"))]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset.filter(is_active=True)
        if self.value() == "N":
            return queryset.filter(is_active=False)
        return queryset

    def choices(self, cl):
        for lookup, title in self.lookup_choices:
            yield {
                "selected": self.value() == lookup,
                "query_string": cl.get_query_string(
                    {
                        self.parameter_name: lookup,
                    },
                    [],
                ),
                "display": title,
            }


class LocalGroupFilter(SimpleListFilter):
    title = _("local groups")
    parameter_name = "local_group"

    def lookups(self, request, model_admin):
        return [(group.id, group.name) for group in LocalGroup.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(groups=self.value())
        return queryset


class PermissionGroupFilter(SimpleListFilter):
    title = _("permission groups")
    parameter_name = "permission_group"

    def lookups(self, request, model_admin):
        local_group_ids = LocalGroup.objects.values_list("group_ptr", flat=True)
        return [(group.id, group.name) for group in Group.objects.exclude(id__in=local_group_ids)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(groups=self.value())
        return queryset


# Modified from django.contrib.auth.admin.UserAdmin to remove username field
class UserAdmin(admin.ModelAdmin):
    add_form_template = "admin/auth/user/add_form.html"
    change_user_password_template = None
    fieldsets = (
        (None, {"fields": ("password",)}),
        (
            _("Personal info"),
            {
                "fields": (
                    "member_identifier",
                    "member_type",
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "address",
                    "postal_code",
                    "city",
                    "cadre",
                    "extra_information",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "date_left")}),
        # ("Membership", {"fields": ("subscription_set",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "password1",
                    "password2",
                    "member_identifier",
                    "first_name",
                    "last_name",
                    "email",
                ),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined", "date_left", "is_active")
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ("email", "first_name", "last_name", "is_staff")
    list_filter = (
        "is_staff",
        "is_superuser",
        IsActiveFilter,
        LocalGroupFilter,
        PermissionGroupFilter,
        "cadre",
    )

    search_fields = ("first_name", "last_name", "email")
    ordering = ("email",)
    filter_horizontal = (
        "groups",
        "user_permissions",
    )
    delete_confirmation_template = "admin/members/membership_cancellation_confirm.html"

    # inlines = (MembershipInline,)

    def get_changeform_initial_data(self, request):
        return {"member_identifier": generate_member_number()}

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return self.readonly_fields + ("member_identifier",)
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form during user creation
        """
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def get_urls(self):
        return [
            path(
                "<id>/password/",
                self.admin_site.admin_view(self.user_change_password),
                name="auth_user_password_change",
            ),
        ] + super().get_urls()

    def lookup_allowed(self, lookup, value):
        # Don't allow lookups involving passwords.
        return not lookup.startswith("password") and super().lookup_allowed(lookup, value)

    @sensitive_post_parameters_m
    @csrf_protect_m
    def add_view(self, request, form_url="", extra_context=None):
        with transaction.atomic(using=router.db_for_write(self.model)):
            return self._add_view(request, form_url, extra_context)

    def _add_view(self, request, form_url="", extra_context=None):
        # It's an error for a user to have add permission but NOT change
        # permission for users. If we allowed such users to add users, they
        # could create superusers, which would mean they would essentially have
        # the permission to change users. To avoid the problem entirely, we
        # disallow users from adding users if they don't have change
        # permission.
        if not self.has_change_permission(request):
            if self.has_add_permission(request) and settings.DEBUG:
                # Raise Http404 in debug mode so that the user gets a helpful
                # error message.
                raise Http404(
                    'Your user does not have the "Change user" permission. In '
                    "order to add users, Django requires that your user "
                    'account have both the "Add user" and "Change user" '
                    "permissions set."
                )
            raise PermissionDenied
        if extra_context is None:
            extra_context = {}
        username_field = self.model._meta.get_field(self.model.USERNAME_FIELD)
        defaults = {
            "auto_populated_fields": (),
            "username_help_text": username_field.help_text,
        }
        extra_context.update(defaults)
        return super().add_view(request, form_url, extra_context)

    @sensitive_post_parameters_m
    def user_change_password(self, request, id, form_url=""):
        user = self.get_object(request, unquote(id))
        if not self.has_change_permission(request, user):
            raise PermissionDenied
        if user is None:
            raise Http404(
                f"{self.model._meta.verbose_name} object with primary key {escape(id)!r} does not exist."
            )
        if request.method == "POST":
            form = self.change_password_form(user, request.POST)
            if form.is_valid():
                form.save()
                change_message = self.construct_change_message(request, form, None)
                self.log_change(request, user, change_message)
                msg = "Password changed successfully."
                messages.success(request, msg)
                update_session_auth_hash(request, form.user)
                return HttpResponseRedirect(
                    reverse(
                        f"{self.admin_site.name}:{user._meta.app_label}_{user._meta.model_name}_change",
                        args=(user.pk,),
                    )
                )
        else:
            form = self.change_password_form(user)

        fieldsets = [(None, {"fields": list(form.base_fields)})]
        adminForm = admin.helpers.AdminForm(form, fieldsets, {})

        context = {
            "title": f"Change password: {escape(user.get_username())}",
            "adminForm": adminForm,
            "form_url": form_url,
            "form": form,
            "is_popup": (IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET),
            "is_popup_var": IS_POPUP_VAR,
            "add": True,
            "change": False,
            "has_delete_permission": False,
            "has_change_permission": True,
            "has_absolute_url": False,
            "opts": self.model._meta,
            "original": user,
            "save_as": False,
            "show_save": True,
            **self.admin_site.each_context(request),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.change_user_password_template or "admin/auth/user/change_password.html",
            context,
        )

    def response_add(self, request, obj, post_url_continue=None):
        """
        Determine the HttpResponse for the add_view stage. It mostly defers to
        its superclass implementation but is customized because the User model
        has a slightly different workflow.
        """
        # We should allow further modification of the user just added i.e. the
        # 'Save' button should behave like the 'Save and continue editing'
        # button except in two scenarios:
        # * The user has pressed the 'Save and add another' button
        # * We are adding a user in a popup
        if "_addanother" not in request.POST and IS_POPUP_VAR not in request.POST:
            request.POST = request.POST.copy()
            request.POST["_continue"] = 1
        return super().response_add(request, obj, post_url_continue)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context.update({"delete_is_cancel": True})
        return super().render_change_form(request, context, add, change, form_url, obj)

    def delete_model(self, request, obj: User):
        obj.is_active = False
        obj.date_left = timezone.now()
        obj.save()

    def has_delete_permission(self, request, obj: User = None):
        if obj is None:
            return super().has_delete_permission(request, obj)
        if obj.date_left is not None:
            return False
        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj: User = None):
        if obj is None:
            return super().has_change_permission(request, obj)
        if obj.date_left is not None:
            return False
        return super().has_change_permission(request, obj)


# Proxy for a separate view with only members on the admin page
class Member(User):
    class Meta(User.Meta):
        verbose_name = _("member")
        verbose_name_plural = _("members")
        proxy = True


@admin.register(Member)
class MemberAdmin(UserAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(member_type=User.MemberType.MEMBER)


# Proxy for a separate view with only support members on the admin page
class SupportMember(User):
    class Meta(User.Meta):
        verbose_name = _("support member")
        verbose_name_plural = _("support members")
        proxy = True


@admin.register(SupportMember)
class SupportMemberAdmin(UserAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(member_type=User.MemberType.SUPPORT_MEMBER)


@admin.register(LocalGroup)
class LocalGroupAdmin(admin.ModelAdmin):
    exclude = ("permissions",)
    filter_horizontal = ("contact_people",)
