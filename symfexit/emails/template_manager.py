from symfexit.emails.base_template import BaseLayout, BaseTemplate
from symfexit.emails.emaillayouts.layout_template import LayoutTemplate
from symfexit.emails.emailtemplates.apply_template import ApplyTemplate
from symfexit.emails.emailtemplates.contact_new_member_template import ContactNewMemberTemplate
from symfexit.emails.emailtemplates.request_new_password_template import RequestNewPasswordTemplate
from symfexit.emails.emailtemplates.welcome_support_template import WelcomeSupportTemplate
from symfexit.emails.emailtemplates.welcome_template import WelcomeTemplate


class LayoutManager:
    templates: list[BaseLayout] = [LayoutTemplate()]

    def get_templates_dict():
        data = {}
        for t in LayoutManager.templates:
            data[t.identifier] = t
        return data

    def get_template_identifiers():
        return [t.identifier for t in LayoutManager.templates]

    def find(identifier: str) -> BaseLayout:
        return LayoutManager.get_templates_dict()[identifier]

    def get_template_choices():
        data = []
        for t in LayoutManager.templates:
            data.append((t.identifier, t.label))
        return data


class TemplateManager:
    templates: list[BaseTemplate] = [
        WelcomeTemplate(),
        ApplyTemplate(),
        ContactNewMemberTemplate(),
        WelcomeSupportTemplate(),
        RequestNewPasswordTemplate(),
    ]

    def get_templates_dict():
        data = {}
        for t in TemplateManager.templates:
            data[t.identifier] = t
        return data

    def get_template_identifiers():
        return [t.identifier for t in TemplateManager.templates]

    def find(identifier: str) -> BaseTemplate:
        return TemplateManager.get_templates_dict()[identifier]

    def get_template_choices():
        data = []
        for t in TemplateManager.templates:
            data.append((t.identifier, t.label))
        return data
