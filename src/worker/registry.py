class TaskRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, name=None):
        def _register(func):
            self._registry[name or func.__name__] = func
            return func
        return _register

    def execute(self, task, *args, **kwargs):
        return self._registry[task.name](*args, **kwargs)

    def __contains__(self, key):
        return key in self._registry

task_registry = TaskRegistry()

def add_task(name, *args, **kwargs):
    from worker.models import Task
    task = Task.objects.create(name=name)
    return task
