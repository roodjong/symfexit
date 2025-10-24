import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, TypedDict

from django.core.mail import send_mail
from django.template import Context, Template
from django.utils.translation import gettext_lazy as _

from symfexit.root.settings import SINGLE_SITE_DOMAIN

if TYPE_CHECKING:
    from symfexit.emails.models import EmailTemplate


class RequiredContext(TypedDict):
    pass


class GivenContext(TypedDict):
    org: str
    date: str
    site: str


class TemplateContext(RequiredContext, GivenContext):
    pass


class BaseTemplate[T: RequiredContext, U: GivenContext]:
    def __init__(self, identifier, label, context: U | T, required: list[str] = None):
        self.identifier = identifier
        self.label = label
        self.context = {
            "org": _("Organisation"),
            "date": _("The date of today in iso format"),
            "site": _("The link to the website"),
            **context,
        }
        self.required = required or []

    @dataclass
    class TemplateValidation:
        formatted_template: str
        unknown_context_keys: list[str]
        missing_context_keys: list[str]

    def validate_template(self, template_text: str) -> TemplateValidation:
        # Check if used keys are correctly spelled, if not return list of all possible and also return wrongly spelled/missing keys
        unknown_keys = []
        missing_keys = [*self.required]  # copy list

        # Replace function
        def replace_keys(match):
            key = match.group(1).strip()  # Get the captured group and trim whitespace
            return f"{{{{ {key} }}}}"  # Format it to {{ key }}

        # Perform the replacement
        matches = re.findall(r"{{\s*(.*?)\s*}}", template_text)
        formatted_template = re.sub(r"{{\s*(.*?)\s*}}", replace_keys, template_text)

        for m in matches:
            if m in missing_keys:
                missing_keys.remove(m)
            if m not in self.context.keys():
                unknown_keys.append(m)

        return BaseTemplate.TemplateValidation(formatted_template, unknown_keys, missing_keys)

    def get_base_context(self) -> U:
        return {
            "date": date.today().isoformat(),
            "org": "Symfexit",
            "site": SINGLE_SITE_DOMAIN,
        }

    def send_mail(  # noqa: PLR0913
        self,
        context: T,  # partially allowed
        recipient_list: list[str] | str,
        lang: str | None = None,
        subject: str | None = None,
        message: str | None = None,
        from_email: str | None = None,
        fail_silently: bool = None,
        html_message: str | None = None,
    ):
        if isinstance(recipient_list, str):
            recipient_list = [recipient_list]

        from symfexit.emails.models import EmailTemplate

        template = EmailTemplate.objects.filter(template=self.identifier).first()
        # in case we add lang, to send mails into base language.
        if lang:
            template = (
                EmailTemplate.objects.filter(template=self.identifier).filter(lang=lang).first()
            )
        if not template:
            raise Exception("No template found to send mail to, please add")

        rendered_subject, rendered_body = self.render(template, context, lang)
        rendered_text_body = self.render_text_body(template, context, lang)

        mail = {
            "subject": subject or rendered_subject,
            "message": message or rendered_text_body,
            "html_message": html_message or rendered_body,
            "from_email": from_email or template.from_email,
            "recipient_list": recipient_list,
            "fail_silently": fail_silently or False,
        }
        send_mail(**mail)

    def render(self, template: "EmailTemplate", context: T, lang: str = None):
        return (
            self.render_subject(template, context, lang),
            self.render_body(template, context, lang),
        )

    def render_body(self, template: "EmailTemplate", context: T, lang: str = None):
        ctx = {**self.get_base_context(), **context}

        body = Template(template.body)
        html = body.render(Context(ctx))

        # if template.
        ctx["content"] = html

        return html

    def render_subject(self, template: "EmailTemplate", context: T, lang: str = None):
        ctx = {**self.get_base_context(), **context}

        subject = Template(template.subject)
        html = subject.render(Context(ctx))
        return html

    def render_text_body(self, template: "EmailTemplate", context: T, lang: str = None):
        ctx = {**self.get_base_context(), **context}

        subject = Template(template.text_body)
        html = subject.render(Context(ctx))
        return html
