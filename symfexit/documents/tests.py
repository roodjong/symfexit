# Create your tests here.

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.documents.models import Directory


def text_contents(response: HttpResponse):
    soup = BeautifulSoup(response.content, features="html.parser")

    for script in soup(["script", "style"]):
        script.extract()

    text = soup.get_text()

    # break into lines and remove leading and trailing space on each
    lines = (line.strip() for line in text.splitlines())
    # break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(chunk for chunk in chunks if chunk)

    return text


class TestTrashcan(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.c = TenantClient(self.tenant)
        # English pages for the test
        self.c.cookies.load({settings.LANGUAGE_COOKIE_NAME: "en"})
        User = get_user_model()
        self.user = User.objects.create_user(email="testuser@example.com", is_superuser=True)
        self.c.force_login(self.user)
        self.depth1 = Directory.objects.create(name="depth1", parent=None)
        self.depth2 = Directory.objects.create(name="depth2", parent=self.depth1)
        self.depth3 = Directory.objects.create(name="depth3", parent=self.depth2)
        self.depth4 = Directory.objects.create(name="depth4", parent=self.depth3)

    def test_correct_parent_is_chosen_when_restoring_nested_directories(self):
        # Directory layout like this:
        # /
        # -> depth1
        #   -> depth2
        #     -> depth3
        # .     -> depth4
        # Then, delete the depth3 folder
        # /
        # -> depth1
        #   -> depth2
        # Trashcan contains:
        # depth3 (still has parent depth2)
        #   -> depth4
        # Restoring depth3 should bring the document explorer to the directory depth2 to start restoring (as that was it's old parent)
        # but restoring depth4 should also bring the explorer to directory depth2 as depth3 is in trash, so it doesn't make sense to move there

        self.depth3.trashed_at = "2024-01-01T00:00:00Z"
        self.depth3.save()

        # Restore depth3: should redirect to depth2
        response = self.c.post(
            reverse("documents:move"),
            {
                "node_id": str(self.depth3.id),
            },
            follow=True,
        )
        self.assertRedirects(response, f"/documenten/{self.depth2.id}/?move={self.depth3.id}")

        # Restore depth4: should redirect to depth2, since depth3 is still trashed
        response = self.c.post(
            reverse("documents:move"),
            {
                "node_id": str(self.depth4.id),
            },
            follow=True,
        )
        self.assertRedirects(response, f"/documenten/{self.depth2.id}/?move={self.depth4.id}")

    def test_trashcan_in_breadcrumbs_when_in_trashed_children(self):
        # Check that the breadcrumbs say "Trashcan" instead of "Documents":
        # Move depth3 to trash
        self.depth3.trashed_at = "2024-01-01T00:00:00Z"
        self.depth3.save()

        # Visit the trashed directory's page
        response = self.c.get(reverse("documents:documents", args=[self.depth3.id]))
        text_content = text_contents(response)
        self.assertIn("Path: Trashcan", text_content)
        # Should not contain "Documents" as the main breadcrumb
        self.assertNotIn("Path: Documents", text_content)
