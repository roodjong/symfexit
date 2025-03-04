import os
import subprocess

from django.conf import settings

from symfexit.theme.models import CurrentThemeVersion
from symfexit.theme.utils import get_theme_filename, get_time_millis
from symfexit.worker import logger
from symfexit.worker.registry import task_registry

NPM_COMMAND = os.getenv("NPM_COMMAND", "npm")
THEME_SRC_DIR = os.getenv("THEME_SRC_DIR", str(settings.BASE_DIR / "theme" / "static_src"))


@task_registry.register("rebuild_theme")
def rebuild_theme():
    logger.log("Rebuilding theme")
    input_css = settings.BASE_DIR / "theme" / "static_src" / "src" / "styles.css"
    new_env = os.environ.copy()
    new_env["NODE_ENV"] = "production"
    version = get_time_millis()
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
            cwd=THEME_SRC_DIR,
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
