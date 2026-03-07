from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from symfexit.adminsite.management.commands.create_permission_groups import (
    Command as CreatePermissionGroupsCommand,
)
from symfexit.adminsite.models import WellKnownPermissionGroup
from symfexit.documents.models import Directory, File
from symfexit.emails.models import EmailLayout, EmailTemplate
from symfexit.events.models import Event
from symfexit.home.models import HomePage
from symfexit.members.models import LocalGroup, User, WorkGroup
from symfexit.membership.models import Membership
from symfexit.signup.models import MembershipApplication
from symfexit.tenants.apps import ensure_single_tenant_if_enabled
from symfexit.tenants.config import config
from symfexit.tenants.models import Client


class Command(BaseCommand):
    help = "Create realistic sample objects for all major models."

    def handle(self, *args, **options):
        # Only allow fixture loading in DEBUG mode
        if not getattr(settings, "DEBUG", False):
            self.stdout.write(self.style.ERROR("Fixture loading is only allowed in DEBUG mode."))
            return

        self.stdout.write(
            self.style.WARNING(
                "This will DELETE ALL DATA in the database for relevant models and reload fixtures."
            )
        )
        confirm = input("Are you sure you want to continue? (yes/no): ").strip().lower()
        if confirm != "yes":
            self.stdout.write(self.style.ERROR("Aborted by user."))
            return

        self.delete_all_data()

        self.recreate_tenant()

        self.load_fixtures()

    def delete_all_data(self):
        # Delete all relevant data
        self.stdout.write(self.style.WARNING("Deleting all data..."))
        File.objects.all().delete()
        Directory.objects.all().delete()
        EmailLayout.objects.all().delete()
        EmailTemplate.objects.all().delete()
        Event.objects.all().delete()
        MembershipApplication.objects.all().delete()
        User.objects.all().delete()
        LocalGroup.objects.all().delete()
        WorkGroup.objects.all().delete()
        Membership.objects.all().delete()
        HomePage.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("All relevant data deleted."))

    def recreate_tenant(self):
        Client.objects.all().delete()

        ensure_single_tenant_if_enabled(None)

    def load_fixtures(self):
        now = timezone.now()

        view_all_group = WellKnownPermissionGroup.get_or_create(
            code=WellKnownPermissionGroup.WellKnownPermissionGroups.VIEW_ALL
        )
        # Create superuser
        superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="Revolution",
            first_name="Admin",
            last_name="User",
        )
        view_all_group.group.user_set.add(superuser)

        board_members = self.create_board_members()
        work_groups = self.create_work_groups()
        local_groups, all_members, contact_people, workgroup_members = self.create_local_groups(
            board_members, work_groups[0]
        )

        self.create_events(board_members, contact_people, all_members, now)

        self.create_documents(work_groups[0])
        # Not creating email templates and layouts
        home = HomePage.objects.create(title="Welcome Home", content="<h1>Home</h1>")
        config.HOMEPAGE_CURRENT = home.pk  # set it to the default home page.
        self.stdout.write(self.style.SUCCESS("Sample objects for all major models created."))

        CreatePermissionGroupsCommand().handle()

    def create_board_members(self):
        board_group = WellKnownPermissionGroup.get_or_create(
            code=WellKnownPermissionGroup.WellKnownPermissionGroups.BOARD
        )
        board_members = []
        for i in range(3):
            user = User.objects.create_user(
                email=f"board{i + 1}@example.com",
                password="Revolution",
                first_name=f"Board{i + 1}",
                last_name="Member",
            )
            board_members.append(user)
            board_group.group.user_set.add(user)
        return board_members

    def create_work_groups(self):
        fixture_workgroup = WorkGroup.objects.create(name="Webteam")
        return [fixture_workgroup]

    def create_local_groups(self, board_members: list[User], workgroup: WorkGroup):
        local_groups = []
        all_members = []
        contact_people = set()
        workgroup_members = []
        contact_person_group = WellKnownPermissionGroup.get_or_create(
            code=WellKnownPermissionGroup.WellKnownPermissionGroups.CONTACT_PERSON
        )
        for g in range(5):
            group = LocalGroup.objects.create(name=f"Local Group {g + 1}")
            local_groups.append(group)
            applications = []
            for m in range(10):
                app = MembershipApplication.objects.create(
                    first_name=f"Member{g + 1}_{m + 1}",
                    last_name="User",
                    email=f"member{g + 1}_{m + 1}@example.com",
                    phone_number=f"06{g + 1}{m + 1}0000",
                    birth_date=date(1990, 1, 1),
                    address=f"{g + 1}{m + 1} Main St",
                    city="Cityville",
                    postal_code=f"{g + 1}{m + 1}2345",
                    payment_amount=1000,
                    preferred_group=group,
                )
                applications.append(app)
            # Accept 8 applications and create users
            accepted_apps = applications[:8]
            # TODO: deny the last application
            group_members = []
            for app in accepted_apps:
                app.status = MembershipApplication.Status.ACCEPTED
                app.save()
                user = app.create_user()
                user.set_password("Revolution")
                user.save()
                group_members.append(user)
                all_members.append(user)
            # Set cadre for first 4 members of the group
            for cadre_user in group_members[:4]:
                cadre_user.cadre = True
                cadre_user.save()
            # Deactivate last 2 members of the group
            for deactivated_user in group_members[-2:]:
                deactivated_user.is_active = False
                deactivated_user.date_left = datetime.now().astimezone() - timedelta(days=1)
                deactivated_user.save()
            # Make last member a support member
            group_members[-3].member_type = User.MemberType.SUPPORT_MEMBER
            group_members[-3].save()
            # First 2 accepted members are contact persons
            for contact in group_members[:2]:
                group.contact_people.add(contact)
                contact_people.add(contact)
                contact_person_group.group.user_set.add(contact)
            # Add member number 3 to a workgroup
            workgroup.workgroup_contact_people.add(group_members[2])
        return local_groups, all_members, contact_people, workgroup_members

    def create_memberships(self, all_members, now):
        for user in all_members:
            active_range = (now - timedelta(days=30), None)
            Membership.objects.create(user=user, active_from_to=active_range)

    def create_events(self, board_members, contact_people, all_members, now):
        event_past = Event.objects.create(
            event_name="Past Event",
            event_organiser="Board",
            event_date=now - timedelta(days=10, hours=2),
            event_end=now - timedelta(days=10),
            event_desc="An event that happened in the past.",
        )
        event_ongoing = Event.objects.create(
            event_name="Ongoing Event",
            event_organiser="Board",
            event_date=now,
            event_end=now + timedelta(hours=6),
            event_desc="An event that is happening right now.",
        )
        event_future = Event.objects.create(
            event_name="Future Event",
            event_organiser="Board",
            event_date=now + timedelta(days=5, hours=3),
            event_end=now + timedelta(days=5, hours=6),
            event_desc="An event you are attending.",
        )
        event_future_no_attendees = Event.objects.create(
            event_name="Future Event",
            event_organiser="Group 1",
            event_date=now + timedelta(days=5, hours=3),
            event_end=now + timedelta(days=5, hours=6),
            event_desc="An event you do not attend.",
        )
        for event in [event_past, event_ongoing, event_future]:
            event.attendees.set([*board_members, *all_members])
        return [event_past, event_ongoing, event_future, event_future_no_attendees]

    def create_documents(self, workgroup: WorkGroup):
        root_dir = Directory.objects.create(name="root")
        dirs = []
        files = []
        for i in range(3):
            sub_dir = Directory.objects.create(name=f"subfolder_{i + 1}", parent=root_dir)
            File.objects.create(
                name="README.md",
                parent=sub_dir,
            ).content.save("README.md", ContentFile(f"# Readme for subfolder {i + 1}".encode()))
            dirs.append(sub_dir)
            for j in range(2):
                File.objects.create(
                    name=f"file_{j + 1}.txt",
                    parent=sub_dir,
                ).content.save(
                    f"file_{j + 1}.txt",
                    ContentFile(f"Sample content {j + 1} in subfolder {i + 1}".encode()),
                )
                files.append(sub_dir)
        dirs[-1].owner = workgroup
        dirs[-1].save()
        return files, dirs
