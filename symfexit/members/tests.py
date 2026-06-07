from django.contrib.auth import get_user_model
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

User = get_user_model()


class MembersPageTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        # Log in a test user
        self.client.force_login(User.objects.create_superuser(email="testuser@example.com"))

    def test_members_page_loads(self):
        response = self.client.get("/admin/members/member/")
        self.assertEqual(response.status_code, 200)

    def test_members_filters_loads(self):
        response = self.client.get(
            "/admin/members/member/",
            {
                "cadre__exact": 1,
                "is_active": "N",
                "is_staff__exact": 0,
                "is_superuser__exact": 1,
                "permission_group": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
