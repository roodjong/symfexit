import io
import pickle
import traceback

from django.apps import apps
from django.conf import settings
from django.db import connection, models
from django.utils import timezone


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
        from symfexit.worker import logger
        from symfexit.worker.models import Task

        args = DBUnpickler(io.BytesIO(task.args)).load()
        kwargs = DBUnpickler(io.BytesIO(task.kwargs)).load()
        logger.clear()
        try:
            self._registry[task.name](*args, **kwargs)
        except Exception as e:
            task.status = Task.Status.EXCEPTION
            logoutput = logger.get_output()
            task.output = (
                f"{logoutput}\n\nTask failed with exception ({type(e)}): {traceback.format_exc()}"
            )
            return
        else:
            logoutput = logger.get_output()
            task.output = logoutput
            task.status = Task.Status.COMPLETED
        finally:
            task.completed_at = timezone.now()
            task.save()


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
    if settings.RUN_TASKS_SYNC:
        task_registry.execute(task)
    return task
