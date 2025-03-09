import io
import pickle

from django.apps import apps
from django.conf import settings
from django.db import connection, models


class DBPickler(pickle.Pickler):
    def persistent_id(self, obj):
        if isinstance(obj, models.Model) and obj.pk is not None:
            return f"{obj._meta.app_label}.{obj._meta.model_name}", obj.pk
        return None


class DBUnpickler(pickle.Unpickler):
    def persistent_load(self, pid):
        fq_model, pk = pid
        app_label, model_name = fq_model.split(".")
        model = apps.get_model(app_label, model_name)
        return model.objects.get(pk=pk)


class TaskRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, name):
        def _register(func):
            self._registry[name] = func
            return func

        return _register

    def execute(self, task):
        args = DBUnpickler(io.BytesIO(task.args)).load()
        kwargs = DBUnpickler(io.BytesIO(task.kwargs)).load()
        return self._registry[task.name](*args, **kwargs)

    def __contains__(self, key):
        return key in self._registry


task_registry = TaskRegistry()


def add_task(name, *args, **kwargs):
    from symfexit.worker.models import Task

    if name not in task_registry:
        raise ValueError(f"Unknown task {name}")

    args_bytes = io.BytesIO()
    DBPickler(args_bytes).dump(args)
    kwargs_bytes = io.BytesIO()
    DBPickler(kwargs_bytes).dump(kwargs)

    task = Task.objects.create(
        name=name, args=args_bytes.getvalue(), kwargs=kwargs_bytes.getvalue(), tenant=connection.tenant
    )
    with connection.cursor() as cursor:
        cursor.execute("NOTIFY worker_task, %s;", [str(task.id)])
    if settings.RUN_TASKS_SYNC:
        task_registry.execute(task)
    return task
