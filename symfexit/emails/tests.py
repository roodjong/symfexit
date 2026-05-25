from typing import TypedDict

from django.core import mail
from django.template import Context, Template
from django.test import TestCase, override_settings

# from unittest.mock import patch  # removed, not used anymore
# Import the components to be tested
from symfexit.emails._templates.base import (
    BaseEmailComponent,
    BodyTemplate,
    WrapperLayout,
)
from symfexit.emails._templates.manager import EmailTemplateManager
from symfexit.emails._templates.render import send_email
from symfexit.emails.admin import EmailLayoutForm, EmailTemplateForm
from symfexit.emails.models import EmailTemplate
from symfexit.tenants.test import override_config

BASE_CONTEXT = {
    "site_title": "Test Site",
    "site_url": "https://example.com",
    "site_logo": "https://example.com/static/logo.png",
}


class EmailComponentTests(TestCase):
    """
    Django-style unit tests for the email component system.
    """

    def setUp(self):
        # Base context that all tests will use
        self.base_context = BASE_CONTEXT

        # Custom context that extends the base one
        self.custom_context = self.base_context.copy()
        self.custom_context["custom_key"] = "Custom value"

    # ---------------------------------------------------------------------
    # Tests for BaseEmailComponent
    # ---------------------------------------------------------------------
    @override_config(
        SITE_TITLE=BASE_CONTEXT["site_title"],
        MAIN_SITE=BASE_CONTEXT["site_url"],
        LOGO_IMAGE="logo.png",
    )
    def test_get_context_values(self):
        """BaseEmailComponent.get_context_values() merges base context correctly."""
        ctx = BaseEmailComponent.get_context_values()

        self.assertEqual(ctx["site_title"], self.base_context["site_title"])
        self.assertEqual(ctx["site_url"], self.base_context["site_url"])
        self.assertEqual(
            ctx["site_logo"],
            f"{self.base_context['site_url']}/media/logo.png",
        )

    @override_config(
        SITE_TITLE=BASE_CONTEXT["site_title"],
        MAIN_SITE=BASE_CONTEXT["site_url"],
        LOGO_IMAGE="logo.png",
    )
    def test_get_context_options(self):
        """The options dictionary contains the base keys and the input keys."""
        opts = BaseEmailComponent.get_context_options()

        # Base keys should be present
        self.assertIn("site_title", opts)
        self.assertIn("site_url", opts)
        self.assertIn("site_logo", opts)

        # No input keys by default
        self.assertNotIn("content", opts)

    @override_config(
        SITE_TITLE=BASE_CONTEXT["site_title"],
        MAIN_SITE=BASE_CONTEXT["site_url"],
        LOGO_IMAGE="logo.png",
    )
    def test_wrapper_layout_get_input_context(self):
        """WrapperLayout adds the 'content' key to the input context."""
        opts = WrapperLayout.get_context_options()

        self.assertIn("content", opts)
        # The content key is required
        self.assertTrue(opts["content"][1] is True)

    @override_config(
        SITE_TITLE="Site",
        MAIN_SITE="https://site.com",
        LOGO_IMAGE="logo.png",
    )
    def test_validate_template_known_and_unknown_keys(self):
        """BaseEmailComponent.validate_template correctly identifies unknown and missing keys."""
        template = (
            "Hello {{ site_title }}, check out {{ site_url }}, "
            "and this is a {{ missing_key }} and an {{ unknown }}."
        )
        result = WrapperLayout.validate_template(template)

        expected_formatted = (
            "Hello {{ site_title }}, check out {{ site_url }}, "
            "and this is a {{ missing_key }} and an {{ unknown }}."
        )
        self.assertEqual(result.formatted_template, expected_formatted)

        # Missing keys (site_logo is required but not present)
        self.assertEqual(set(result.missing_context_keys), {"content"})

        # Unknown keys
        self.assertEqual(set(result.unknown_context_keys), {"missing_key", "unknown"})

    # ---------------------------------------------------------------------
    # Tests for rendering & sending emails
    # ---------------------------------------------------------------------
    def test_render_email_template(self):
        """Rendering a Django template with the base context works."""
        template_text = (
            "Title: {{ site_title }}\n"
            "URL: {{ site_url }}\n"
            "Logo: {{ site_logo }}\n"
            "Custom: {{ custom_key }}\n"
        )
        django_template = Template(template_text)

        # Merge the base context from the component with the custom one
        context = {**BaseEmailComponent.get_context_values(), **self.custom_context}
        rendered = django_template.render(Context(context))

        self.assertIn("Title: Test Site", rendered)
        self.assertIn("URL: https://example.com", rendered)
        self.assertIn("Logo: https://example.com/static/logo.png", rendered)
        self.assertIn("Custom: Custom value", rendered)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    def test_send_email_via_backend(self):
        """
        If a send_email helper exists, it should use Django's email backend.
        The test is written defensively – it will simply skip if the helper
        is not present in this repository.
        """

        class ApplyContext(TypedDict):
            custom_key: str

        class TestEmail(BodyTemplate[ApplyContext]):
            code = "test"
            label = "Test template"

            @classmethod
            def get_input_context(cls):
                return [
                    *super().get_input_context(),
                    {"custom_key": "First name of the member"},
                ]

            pass

            subject_template = "Welcome to {{ site_title }}"
            html_template = "Hello {{ custom_key }}, thanks for joining {{ site_title }}."
            text_template = "Hello {{ custom_key }}, thanks for joining {{ site_title }}."

        # Call the helper – the helper is expected to send an email and return
        # the email instance that Django's mail backend stores.
        send_email(
            TestEmail({"custom_key": "Custom value"}),
            recipient_list=["user@example.com"],
            from_email="noreply@example.com",
        )

        # Verify that the email is queued by the locmem backend
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, "Welcome to Membersite")
        self.assertEqual(sent_email.to, ["user@example.com"])
        self.assertNotIn("User@example.com", sent_email.body)  # sanity check
        self.assertIn("Custom value", sent_email.body)

    def test_every_mail_has_default_template(self):
        for t in EmailTemplateManager._registry:
            assert t.subject_template
            assert t.html_template
            assert t.text_template


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LANGUAGE_CODE="nl-NL",
)
class EmailLanguageFallbackTests(TestCase):
    def setUp(self):
        EmailTemplate.objects.filter(template="test_lang").delete()

        class TestLangEmail(BodyTemplate):
            code = "test_lang"
            label = "Test"
            subject_template = "Subject"
            html_template = "Body"
            text_template = "Text"

        self.template_class = TestLangEmail

        # Create test templates
        for lang, subject in [("en-US", "EN-US"), ("en", "EN"), ("nl", "NL"), ("*", "Fallback")]:
            EmailTemplate.objects.create(
                template="test_lang",
                language=lang,
                from_email="test@example.com",
                subject=subject,
                body=f"Body {subject}",
                text_body=f"Text {subject}",
            )

    def _send_and_check(self, lang, expected_subject):
        """Helper to send email and check the result."""
        send_email(self.template_class({}), recipient_list=["user@example.com"], lang=lang)
        self.assertEqual(mail.outbox[-1].subject, expected_subject)

    def test_exact_match(self):
        self._send_and_check("en-US", "EN-US")

    def test_region_fallback(self):
        self._send_and_check("en-GB", "EN")  # en-GB → en

    def test_generic_fallback(self):
        self._send_and_check("fr", "Fallback")  # fr → *

    def test_none_uses_generic(self):
        self._send_and_check(None, "Fallback")

    def test_priority_order(self):
        self._send_and_check("en-US", "EN-US")
        self._send_and_check("en-GB", "EN")
        EmailTemplate.objects.filter(language__in=["en-US", "en"]).delete()
        self._send_and_check("en-GB", "Fallback")


class EmailAdminFormTests(TestCase):
    def test_email_template_form_requires_template_identifier(self):
        form = EmailTemplateForm(
            data={
                "language": "en",
                "from_email": "test@example.com",
                "subject": "Test",
                "body": "<p>Test</p>",
                "text_body": "Test",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("body", form.errors)

    def test_email_layout_form_requires_template_identifier(self):
        form = EmailLayoutForm(
            data={"name": "Test", "body": "<div>{{ content }}</div>", "text_body": "{{ content }}"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("body", form.errors)
