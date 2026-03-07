# Create your tests here.

import uuid

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from symfexit.documents.decorators import documents_permission_required
from symfexit.documents.models import Directory, File
from symfexit.members.models import WorkGroup


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


class TestDocumentsPermissionRequired(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.c = TenantClient(self.tenant)
        User = get_user_model()
        self.user = User.objects.create_user(email="permuser@example.com", is_superuser=False)
        self.contact_user = User.objects.create_user(
            email="contact@example.com", is_superuser=False
        )
        self.group = Group.objects.create(name="Workgroup")
        self.workgroup = WorkGroup.objects.create(name="WG1")
        self.root = Directory.objects.create(name="root", parent=None)
        self.folder = Directory.objects.create(name="folder", parent=self.root, owner=self.group)
        self.subfolder = Directory.objects.create(name="subfolder", parent=self.folder)
        self.file_in_folder = File.objects.create(name="file1.txt", parent=self.folder)
        self.contact_user.save()
        self.workgroup.workgroup_contact_people.add(self.contact_user)
        self.folder.owner = self.workgroup
        self.folder.save()
        self.contact_user.groups.add(self.workgroup)
        self.factory = RequestFactory()

    def test_permission_granted_by_contact_person(self):
        request = self.factory.post("/documenten/edit", {"node_id": str(self.file_in_folder.id)})
        request.user = self.contact_user

        @documents_permission_required(
            ("documents.change_directory", "documents.change_file"),
            directory_parameter="node_id",
            raise_exception=True,
        )
        def dummy_view(request):
            return HttpResponse("OK")

        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_permission_denied_for_non_contact(self):
        request = self.factory.post("/documenten/edit", {"node_id": str(self.file_in_folder.id)})
        request.user = self.user

        @documents_permission_required(
            ("documents.change_directory", "documents.change_file"),
            directory_parameter="node_id",
            raise_exception=True,
        )
        def dummy_view(request):
            return HttpResponse("OK")

        with self.assertRaises(PermissionDenied):
            dummy_view(request)

    def test_permission_granted_by_perm(self):
        # Grant explicit permissions
        perms = Permission.objects.filter(codename__in=["change_directory", "change_file"])
        self.user.user_permissions.add(*perms)
        request = self.factory.post("/documenten/edit", {"node_id": str(self.file_in_folder.id)})
        request.user = self.user

        @documents_permission_required(
            ("documents.change_directory", "documents.change_file"),
            directory_parameter="node_id",
            raise_exception=True,
        )
        def dummy_view(request):
            return HttpResponse("OK")

        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_permission_denied_missing_node(self):
        # Use a valid UUID that does not exist
        missing_uuid = str(uuid.uuid4())
        request = self.factory.post("/documenten/edit", {"node_id": missing_uuid})
        request.user = self.contact_user

        @documents_permission_required(
            ("documents.change_directory", "documents.change_file"),
            directory_parameter="node_id",
            raise_exception=True,
        )
        def dummy_view(request):
            return HttpResponse("OK")

        with self.assertRaises(PermissionDenied):
            dummy_view(request)


class TestWorkgroupMemberAccess(FastTenantTestCase):
    def setUp(self):
        super().setUp()
        self.c = TenantClient(self.tenant)
        User = get_user_model()
        self.member = User.objects.create_user(email="member@example.com", is_superuser=False)
        self.member.member_type = User.MemberType.MEMBER
        self.member.save()
        self.other_member = User.objects.create_user(
            email="othermember@example.com", is_superuser=False
        )
        self.other_member.member_type = User.MemberType.MEMBER
        self.other_member.save()
        self.wg1 = WorkGroup.objects.create(name="WG1")
        self.wg2 = WorkGroup.objects.create(name="WG2")
        self.folder1 = Directory.objects.create(name="wg1folder", parent=None, owner=self.wg1)
        self.folder2 = Directory.objects.create(name="wg2folder", parent=None, owner=self.wg2)
        self.file1 = File.objects.create(name="wg1file.txt", parent=self.folder1)
        self.file2 = File.objects.create(name="wg2file.txt", parent=self.folder2)
        # Add member to WorkGroup and as contact person
        self.wg1.user_set.add(self.member)
        self.wg2.user_set.add(self.other_member)
        self.wg1.workgroup_contact_people.add(self.member)
        self.wg2.workgroup_contact_people.add(self.other_member)
        self.c.force_login(self.member)

    def test_member_can_access_own_workgroup_folder(self):
        response = self.c.post(
            reverse("documents:edit"), {"node_id": str(self.file1.id), "name": "newname.txt"}
        )
        self.assertEqual(response.status_code, 302, f"Expected 200, got {response.status_code}")

    def test_member_cannot_access_other_workgroup_folder(self):
        response = self.c.post(
            reverse("documents:edit"), {"node_id": str(self.file2.id), "name": "newname.txt"}
        )
        self.assertEqual(
            response.status_code, 403, "Should NOT be able to edit file in another workgroup folder"
        )
