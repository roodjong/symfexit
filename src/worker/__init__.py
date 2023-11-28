from django.utils.module_loading import autodiscover_modules
from worker.logger import Logger
from worker.registry import task_registry

def autodiscover():
    autodiscover_modules("tasks", register_to=task_registry)

logger = Logger()
