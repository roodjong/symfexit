import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.root.management.commands.load_fixtures import Command


@override_settings(LANGUAGE_CODE="en-US", LANGUAGES=(("en", "English"),))
class AdminViewTests(FastTenantTestCase):
    def setUp(self):
        Command().delete_all_data()
        Command().load_fixtures()

        self.client = TenantClient(self.tenant)
        User = get_user_model()
        self.superuser = User.objects.get(email="admin@example.com")
        self.client.cookies.load({"django_language": "en"})
        self.client.force_login(self.superuser)
        self.group = Group.objects.create(name="Test Group")

    def test_admin_index(self):
        url = reverse("admin:index")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "administration")

    def test_admin_urls_accessible(self):
        User = get_user_model()
        superuser = User.objects.get(email="admin@example.com")
        self.client.force_login(superuser)
        admin_urls = [
            "/admin/auth/group/",
            "/admin/documents/file/",
            "/admin/documents/directory/",
            "/admin/emails/emaillayout/",
            "/admin/emails/emailtemplate/",
            "/admin/events/event/",
            "/admin/home/homepage/",
            "/admin/members/member/",
            "/admin/members/supportmember/",
            "/admin/members/localgroup/",
            "/admin/members/workgroup/",
            "/admin/members/localgroupmember/",
            "/admin/signup/membershipapplication/",
            "/admin/payments/billingaddress/",
            "/admin/payments/subscription/",
            "/admin/tenants/client/",
            "/admin/theme/tailwindkey/",
        ]

        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed to load {url}")
            overview_html = response.content.decode()
            # Check for add button
            add_url = url + "add/"
            if add_url in overview_html:
                response = self.client.get(add_url)
                self.assertIn(response.status_code, [200], f"Add page not accessible for {add_url}")
            else:
                print(f"No add_url found in HTML for {url}, skipping add page test.")
            # Find a valid object id from overview page
            ids = re.findall(rf"{url}(.*)/change/", overview_html)
            if ids:
                edit_url = url + f"{ids[0]}/change/"
                response = self.client.get(edit_url)
                self.assertIn(
                    response.status_code,
                    [200],
                    f"Edit page not accessible for {edit_url}",
                )
            else:
                print(f"No object ids found for {url}, skipping edit page test.")
