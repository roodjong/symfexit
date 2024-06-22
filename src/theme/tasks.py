import os
import subprocess

from django.conf import settings

from django.utils import timezone

from theme.models import CurrentThemeVersion
from theme.utils import get_theme_filename
from worker import logger
from worker.registry import task_registry

THEME_DIR = os.getenv(
    "THEME_SRC_DIR",
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "static_src"),
)

NPM_COMMAND = os.getenv("NPM_COMMAND", "npm")


@task_registry.register("rebuild_theme")
def rebuild_theme():
    logger.log("Rebuilding theme")
    input_css = settings.BASE_DIR / "theme" / "static_src" / "src" / "styles.css"
    new_env = os.environ.copy()
    new_env["NODE_ENV"] = "production"
    version = timezone.now()
    output_name = get_theme_filename(version)
    stdout = subprocess.check_output(
        [
            NPM_COMMAND,
            "run",
            "tailwindcss",
            "--",
            "--postcss",
            "--minify",
            "-i",
            input_css,
            "-o",
            settings.DYNAMIC_THEME_ROOT / output_name,
        ],
        cwd=THEME_DIR,
        stderr=subprocess.STDOUT,
        env=new_env,
    )
    for line in stdout.decode("utf-8").split("\n"):
        logger.log(line)
    logger.log("Rebuilding theme done")
    CurrentThemeVersion.objects.create(version=version)
