from time import sleep
import traceback
from django.core.management import BaseCommand
from django.core.management.base import CommandParser
from django.db import transaction
from django.utils import timezone
from worker import logger

from worker.models import Task
from worker.registry import task_registry


class Command(BaseCommand):
    help = "Run the worker"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--batch_size", type=int, default=10)

    def handle(self, *args, **options):

        self.stdout.write("Starting worker")
        last_sleep = 0
        while True:
            tasks = (
                Task.objects.select_for_update(skip_locked=True)
                .filter(status=Task.STATUS_QUEUED)
                .order_by("created_at")
            )[: options["batch_size"]]
            tasks_amount = len(tasks)

            with transaction.atomic():
                for task in tasks:
                    logger.clear()
                    task.picked_up_at = timezone.now()
                    if task.name not in task_registry:
                        task.status = Task.STATUS_ERROR_UNKNOWN_TASK
                        task.save()
                        self.stdout.write(f"Unknown task {task.name}, marking as error")
                        continue
                    try:
                        task_registry.execute(task)
                    except Exception as e:
                        task.status = Task.STATUS_EXCEPTION
                        logoutput = logger.get_output()
                        task.output = f"{logoutput}\n\nTask failed with exception ({type(e)}): {traceback.format_exc()}"
                        self.stdout.write(f"Exception in task {task.name}: {e}")
                        continue
                    else:
                        logoutput = logger.get_output()
                        task.output = logoutput
                        task.status = Task.STATUS_COMPLETED
                        self.stdout.write(f"Completed task {task.name}")
                    finally:
                        task.completed_at = timezone.now()
                        task.save()

            if tasks_amount == 0:
                sleep_time = min(max(1, last_sleep), 4)
                last_sleep = sleep_time * 2
                sleep(sleep_time)
            else:
                last_sleep = 0
