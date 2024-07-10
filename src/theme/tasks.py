import os
import subprocess

from django.conf import settings

from django.utils import timezone

from theme.models import CurrentThemeVersion
from theme.utils import get_theme_filename
from worker import logger
from worker.registry import task_registry

NPM_COMMAND = os.getenv("NPM_COMMAND", "npm")


@task_registry.register("rebuild_theme")
def rebuild_theme():
    logger.log("Rebuilding theme")
    input_css = settings.BASE_DIR / "theme" / "static_src" / "src" / "styles.css"
    theme_dir = settings.BASE_DIR / "theme" / "static_src"
    new_env = os.environ.copy()
    new_env["NODE_ENV"] = "production"
    version = timezone.now()
    output_name = get_theme_filename(version)
    try:
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
            cwd=theme_dir,
            stderr=subprocess.STDOUT,
            env=new_env,
        )
        for line in stdout.decode("utf-8").split("\n"):
            logger.log(line)
        logger.log("Rebuilding theme done")
        CurrentThemeVersion.objects.create(version=version)
    except subprocess.CalledProcessError as e:
        logger.log("Rebuilding theme failed")
        for line in e.output.decode("utf-8").split("\n"):
            logger.log(line)
        return
