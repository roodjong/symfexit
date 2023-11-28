import os
import subprocess
from worker import logger
from worker.registry import task_registry

THEME_DIR = os.getenv(
    "THEME_SRC_DIR",
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "static_src"),
)


@task_registry.register("rebuild_theme")
def rebuild_theme():
    logger.log("Rebuilding theme")
    stdout = subprocess.check_output(
        ["npm", "run", "build:tailwind"], cwd=THEME_DIR, stderr=subprocess.STDOUT
    )
    for line in stdout.decode("utf-8").split("\n"):
        logger.log(line)
    logger.log("Rebuilding theme done")
