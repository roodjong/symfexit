from django.core.management import BaseCommand
from django.core.management.base import CommandParser
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from symfexit.worker.models import Task
from symfexit.worker.registry import task_registry


class Command(BaseCommand):
    help = "Run the worker"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch_size", type=int, default=10)

    def handle(self, *args, **options):
        self.stdout.write("Starting worker")
        listen_connection = connections.create_connection(DEFAULT_DB_ALIAS).cursor().connection
        listen_connection.execute("LISTEN worker_task")
        notifies = listen_connection.notifies()
        # Process any pending notifications
        with transaction.atomic():
            tasks = (
                Task.objects.select_for_update(skip_locked=True)
                .filter(status=Task.Status.QUEUED)
                .order_by("created_at")
            )[: options["batch_size"]]
            for task in tasks:
                self.handle_task(task)
        # LISTEN for any NOTIFYs and handle them
        for notify in notifies:
            task_id = int(notify.payload)
            with transaction.atomic():
                task = (
                    Task.objects.select_for_update(skip_locked=True)
                    .filter(status=Task.Status.QUEUED, id=task_id)
                    .first()
                )
                if task is None:
                    continue
                self.handle_task(task)

    def handle_task(self, task):
        task.picked_up_at = timezone.now()
        if task.name not in task_registry:
            task.status = Task.Status.ERROR_UNKNOWN_TASK
            task.save()
            self.stdout.write(f"Unknown task {task.name}, marking as error")
            return

        with tenant_context(task.tenant):
            task_registry.execute(task)

        if task.status == Task.Status.COMPLETED:
            self.stdout.write(f"Task {task.name} completed")
        elif task.status == Task.Status.EXCEPTION:
            self.stdout.write(f"Task {task.name} failed with exception")
