# Check if used keys are correctly spelled, if not return list of all possible and also return wrongly spelled/missing keys
# symfexit/emails/admin.py
from typing import Any

from django import forms
from django.contrib import admin
from django.forms.utils import ErrorList
from django.utils.translation import gettext_lazy as _

from symfexit.emails._templates.manager import EmailLayoutManager, EmailTemplateManager
from symfexit.emails.models import EmailLayout, EmailTemplate


# ----------------------------------------------------------------------
# Helper: Validate template context keys
# ----------------------------------------------------------------------
def check_ctx_keys_correct(
    template,
    ctx_dict: dict[str, tuple[str, bool]],
    data: dict,
    _errors: Any,
    field_key: str,
    value: str,
    missing: bool = True,
) -> dict[str, ErrorList]:
    """
    Validate a template string against its expected context keys, update the
    cleaned ``data`` dictionary, and collect any errors.

    Parameters
    ----------
    template
        Object providing a :py:meth:`validate_template` method that returns an
        object with ``formatted_template``, ``missing_context_keys`` and
        ``unknown_context_keys`` attributes.
    ctx_dict
        Mapping of context key names to a tuple ``(description, is_required)``.
    data
        Mutable mapping where the formatted template will be stored under
        ``field_key``.
    _errors
        Mutable mapping that holds :class:`django.forms.utils.ErrorList` for
        each field; it is mutated in place.
    field_key
        The form field name being validated.
    value
        The raw string entered by the user.
    missing
        If ``True`` (default), report missing *required* keys; if ``False``
        only unknown keys are reported.

    Returns
    -------
    MutableMapping[str, ErrorList]
        The (mutated) ``_errors`` mapping.
    """
    # Run the template validator and store the formatted string
    validation_result = template.validate_template(value)
    data[field_key] = validation_result.formatted_template

    missing_keys = validation_result.missing_context_keys
    unknown_keys = validation_result.unknown_context_keys

    # Report errors if there are unknown keys or (when ``missing`` is True)
    # any required keys are missing.
    if unknown_keys or (missing and missing_keys):
        error_messages = []

        # Missing required keys (grouped)
        if missing and missing_keys:
            # Show the missing keys in a comma‑separated list
            missing_list = ", ".join(f"{{{{{mk}}}}}" for mk in missing_keys)
            error_messages.append(_("The following required keys are missing: %s") % missing_list)

        # Unknown keys (grouped)
        if unknown_keys:
            unknown_list = ", ".join(f"{{{{{uk}}}}}" for uk in unknown_keys)
            error_messages.append(_("The following keys are not recognised: %s") % unknown_list)

        # Show all allowed keys (with a '*' for required ones)
        error_messages.append(_("Allowed keys:"))
        for key, (description, required) in ctx_dict.items():
            required_flag = "*" if required else ""
            error_messages.append(f"  - {{{{{key}}}}}: {description} {required_flag}".strip())

        # Attach the nicely formatted errors to the field
        _errors[field_key] = ErrorList(error_messages)

    return _errors


class EmailLayoutForm(forms.ModelForm):
    class Meta:
        model = EmailLayout
        exclude = []  # noqa: DJ006

    def save(self, commit=...):
        return super().save(commit)
        # this function will be used for the validation

    def clean(self):
        # data from the form is fetched using super function
        super().clean()

        body_key = "body"
        text_body_key = "text_body"

        template_identifier = self.cleaned_data.get("template", "")
        body = self.cleaned_data.get(body_key, "")
        text_body = self.cleaned_data.get(text_body_key, "")

        # get template by identifier: template_identifier
        template = EmailLayoutManager.find(template_identifier)
        ctx_dict = template.get_context_options()

        self.data = self.data.copy()

        check_ctx_keys_correct(template, ctx_dict, self.data, self._errors, body_key, body)
        check_ctx_keys_correct(
            template, ctx_dict, self.data, self._errors, text_body_key, text_body
        )

        return self.cleaned_data


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        exclude = []  # noqa: DJ006

    def save(self, commit=...):
        return super().save(commit)
        # this function will be used for the validation

    def clean(self):
        # data from the form is fetched using super function
        super().clean()

        subject_key = "subject"
        body_key = "body"
        text_body_key = "text_body"

        template_identifier = self.cleaned_data.get("template", "")
        subject = self.cleaned_data.get(subject_key, "")
        body = self.cleaned_data.get(body_key, "")
        text_body = self.cleaned_data.get(text_body_key, "")

        # get template by identifier: template_identifier
        template = EmailTemplateManager.find(template_identifier)
        ctx_dict = template.get_context_options()

        self.data = self.data.copy()

        check_ctx_keys_correct(
            template, ctx_dict, self.data, self._errors, subject_key, subject, False
        )
        check_ctx_keys_correct(template, ctx_dict, self.data, self._errors, body_key, body)
        check_ctx_keys_correct(
            template, ctx_dict, self.data, self._errors, text_body_key, text_body
        )

        return self.cleaned_data


@admin.register(EmailLayout)
class EmailLayoutAdmin(admin.ModelAdmin):
    form = EmailLayoutForm
    pass


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateForm
    pass
