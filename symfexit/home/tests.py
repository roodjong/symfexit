from constance import config
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.home.models import HomePage

User = get_user_model()

class HomePageTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        # Log in a test user
        self.client.force_login(User.objects.create_user(email="testuser@example.com"))

    def test_uses_home_template(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/home.html")

    def test_custom_homepage_content(self):
        hp = HomePage.objects.create(
            title="Test title",
            content="Test body",
        )
        config.HOMEPAGE_CURRENT = hp.id
        response = self.client.get("/")
        self.assertContains(response, "Test body")

class HomePageAdminTest(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)
        # Log in a test user
        self.client.force_login(User.objects.create_user(email="testuser@example.com", is_staff=True, is_superuser=True))

    @override_settings(LANGUAGE_CODE='en-US', LANGUAGES=(('en', 'English'),))
    def test_change_view(self):
        hp = HomePage.objects.create(
            title="Test title",
            content="Test body",
        )
        response = self.client.get(reverse("admin:home_homepage_change", args=[hp.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Build new homepage")
        self.assertContains(response, "Save and set as current")

    @override_settings(LANGUAGE_CODE='en-US', LANGUAGES=(('en', 'English'),))
    def test_change_view_current(self):
        hp = HomePage.objects.create(
            title="Test title",
            content="Test body",
        )
        config.HOMEPAGE_CURRENT = hp.id
        response = self.client.get(reverse("admin:home_homepage_change", args=[hp.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change current homepage")

    @override_settings(LANGUAGE_CODE='en-US', LANGUAGES=(('en', 'English'),))
    def test_add_view(self):
        response = self.client.post(reverse("admin:home_homepage_add"), {
            "title": "Test title",
            "content": "Test body",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HomePage.objects.count(), 1)

    @override_settings(LANGUAGE_CODE='en-US', LANGUAGES=(('en', 'English'),))
    def test_add_then_set_as_current(self):
        response = self.client.post(reverse("admin:home_homepage_add"), {
            "title": "Test title",
            "content": "Test body",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HomePage.objects.count(), 1)
        hp = HomePage.objects.first()
        response = self.client.post(reverse("admin:home_homepage_change", args=[hp.id]), {
            "title": "Test title",
            "content": "Test body2",
            "_setcurrent": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(config.HOMEPAGE_CURRENT, hp.id)
        response = self.client.get("/")
        self.assertContains(response, "Test body2")

    @override_settings(LANGUAGE_CODE='en-US', LANGUAGES=(('en', 'English'),))
    def test_scripts_are_filtered(self):
        response = self.client.post(reverse("admin:home_homepage_add"), {
            "title": "Test title",
            "content": "<script>alert('XSS')</script>",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HomePage.objects.count(), 1)
        hp = HomePage.objects.first()
        response = self.client.get(reverse("admin:home_homepage_change", args=[hp.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('XSS')</script>")

        config.HOMEPAGE_CURRENT = hp.id

        response = self.client.get("/")
        self.assertNotContains(response, "<script>alert('XSS')</script>")
