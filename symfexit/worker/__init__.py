from django.utils.module_loading import autodiscover_modules

from symfexit.worker.logger import Logger
from symfexit.worker.registry import task_registry


def autodiscover():
    autodiscover_modules("tasks", register_to=task_registry)


logger = Logger()
