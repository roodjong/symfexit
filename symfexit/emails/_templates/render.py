import urllib.parse

from django.core.mail import send_mail
from django.template import Context, Template

from symfexit.emails._templates.base import BodyTemplate
from symfexit.emails._templates.manager import EmailLayoutManager
from symfexit.emails.models import EmailTemplate

DEFAULT_HTML_BODY = """<!DOCTYPE html>
<html>
<head>
<style>
    @font-face {
        font-family: 'HelveticaNeueLTStd';

        font-weight: 500;
        font-style: normal;
        font-display: swap;
    }
    body {
        font-family: 'HelveticaNeueLTStd';
    }
</style>
</head>
<body>
    {{ content }}
</body>
</html>"""

DEFAULT_TEXT_BODY = """{{content}}"""


# allow overriding of all email variables
def send_email(  # noqa: PLR0913
    email_template: BodyTemplate,
    recipient_list: list[str] | str,
    lang: str | None = None,
    subject: str | None = None,
    message: str | None = None,
    from_email: str | None = None,
    fail_silently: bool = False,
    html_message: str | None = None,
):
    if isinstance(recipient_list, str):
        recipient_list = [recipient_list]

    db_email_template = EmailTemplate.objects.filter(template=email_template.code).first()

    rendered_subject, rendered_body, rendered_text_body = render_email(
        email_template, db_email_template
    )

    mail = {
        "from_email": from_email or db_email_template.from_email if db_email_template else None,
        "recipient_list": recipient_list,
        "subject": subject or rendered_subject,
        "message": message or rendered_text_body,
        "html_message": html_message or rendered_body,
        "fail_silently": fail_silently,
    }
    return send_mail(**mail)


def render_email(
    email_template: BodyTemplate, db_email_template: EmailTemplate
) -> tuple[str, str, str]:
    context = email_template.context
    title = render(
        db_email_template.subject if db_email_template else email_template.subject_template, context
    )

    html_content = render(
        db_email_template.body if db_email_template else email_template.html_template, context
    )
    text_content = render(
        db_email_template.text_body if db_email_template else email_template.text_template,
        context,
    )

    # wrap content with layout, if set
    if db_email_template:
        if email_layout := db_email_template.layout:
            layout = EmailLayoutManager.find(email_layout.template)
            context = {**context, **layout.get_context_values()}
            html_content = render(email_layout.body, {**context, "content": html_content})
            text_content = render(email_layout.text_body, {**context, "content": text_content})

    # render the base body, mostly make html file from content
    html = render(DEFAULT_HTML_BODY, {**context, "content": html_content})
    text = render(DEFAULT_TEXT_BODY, {**context, "content": text_content})

    return title, html, text


def render(template_string: str, context: dict):
    template = Template(urllib.parse.unquote(template_string))
    return template.render(Context(context))
