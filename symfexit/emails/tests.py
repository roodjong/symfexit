from django_tenants.test.cases import FastTenantTestCase

from symfexit.emails.template_manager import TemplateManager


class TestTemplateManager(FastTenantTestCase):
    def test_assigned_templates_required_keys_as_key(self):
        for t in TemplateManager.templates:
            test_template = "\n".join([f"{{{{ {key} }}}}" for key in t.context])
            result = t.validate_template(test_template)

            # assert all given keys are also given
            self.assertFalse(result.unknown_context_keys, f"{t.label} has unknown context keys")

            # assert all given keys are never missing
            self.assertFalse(
                result.missing_context_keys, f"{t.label} is missing required keys in the context"
            )
