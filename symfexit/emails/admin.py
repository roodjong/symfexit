from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from symfexit.emails.base_template import BaseTemplate
from symfexit.emails.emailtemplates.welcome_template import WelcomeTemplate
from symfexit.emails.models import EmailLayout, EmailTemplate
from symfexit.emails.template_manager import LayoutManager, TemplateManager


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
        template: BaseTemplate = LayoutManager.find(template_identifier)
        ctx_dict = template.context

        self.data = self.data.copy()

        # Check if used keys are correctly spelled, if not return list of all possible and also return wrongly spelled/missing keys
        def check_ctx_keys_correct(field_key, value, missing=True):
            validation_result = template.validate_template(value)
            self.data[field_key] = validation_result.formatted_template

            if validation_result.unknown_context_keys or (
                missing and validation_result.missing_context_keys
            ):
                self._errors[field_key] = self.error_class(
                    [
                        *[
                            _("Key %s is required, but could not be found") % mk
                            for mk in validation_result.missing_context_keys
                        ],
                        *[
                            _("Key %s could not be found") % uk
                            for uk in validation_result.unknown_context_keys
                        ],
                        _("Allowed keys:"),
                        *[f"{{{{ {k} }}}}: {v}" for k, v in ctx_dict.items()],
                    ]
                )

        check_ctx_keys_correct(body_key, body)
        check_ctx_keys_correct(text_body_key, text_body)

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
        template: BaseTemplate = TemplateManager.find(template_identifier)
        ctx_dict = template.context

        self.data = self.data.copy()

        # Check if used keys are correctly spelled, if not return list of all possible and also return wrongly spelled/missing keys
        def check_ctx_keys_correct(field_key, value, missing=True):
            validation_result = template.validate_template(value)
            self.data[field_key] = validation_result.formatted_template

            if validation_result.unknown_context_keys or (
                missing and validation_result.missing_context_keys
            ):
                self._errors[field_key] = self.error_class(
                    [
                        *[
                            _("Key %s is required, but could not be found") % mk
                            for mk in validation_result.missing_context_keys
                        ],
                        *[
                            _("Key %s could not be found") % uk
                            for uk in validation_result.unknown_context_keys
                        ],
                        _("Allowed keys:"),
                        *[f"{{{{ {k} }}}}: {v}" for k, v in ctx_dict.items()],
                    ]
                )

        check_ctx_keys_correct(subject_key, subject, False)
        check_ctx_keys_correct(body_key, body)
        check_ctx_keys_correct(text_body_key, text_body)
        WelcomeTemplate().send_mail(
            {
                "firstname": "jelle",
                "fullname": "Jelle de Graaf",
                "group": "arnhem",
                "member_id": 1,
                "nextevent": "1 mei",
                "password_url": "reset_pw_link.nl",
            },
            "ik-jelle@hotmail.nl",
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
