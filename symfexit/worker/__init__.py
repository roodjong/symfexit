from django.utils.module_loading import autodiscover_modules

from symfexit.worker.registry import task_registry
from symfexit.worker.workerlogger import Logger


def autodiscover():
    autodiscover_modules("tasks", register_to=task_registry)


logger = Logger()
