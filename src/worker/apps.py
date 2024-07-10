from django.apps import AppConfig

from django.utils.translation import gettext_lazy as _

class WorkerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worker"
    verbose_name = _("Worker")

    def ready(self):
        self.module.autodiscover()
