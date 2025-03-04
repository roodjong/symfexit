# symfexit

[![Tests](https://github.com/roodjong/symfexit/actions/workflows/test.yml/badge.svg)](https://github.com/roodjong/symfexit/actions/workflows/test.yml)

Departure from our old symfony internal site

## Development

There are two ways to get symfexit running locally:
- [Using a devcontainer](#running-using-a-devcontainer)
- [With your local Python and PostgreSQL installations](#running-locally)

Both are described below.

### Running using a devcontainer

If [your editor supports devcontainers](https://containers.dev/supporting#editors) this is the easiest way to start working.

The specifics vary between editors, but you probably need to install a plugin or extension to support devcontainers.
For VSCode, you need the [Remote - Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.

On your machine you need to have [Docker](https://docs.docker.com/get-docker/) installed.

Then, the steps are as follows:
1. Clone the repository: `git clone https://github.com/roodjong/symfexit.git`
2. Open the repository in your editor.
3. You should see a notification that a devcontainer configuration is available. Click on the notification to open the repository in a devcontainer.
4. The devcontainer will build and start, and you will be in a shell inside the devcontainer.

You may need to configure VSCode to use the .venv `uv` created, so that Pylance can follow the dependencies.

Continue following the first time setup steps below.

### Running locally

The recommended setup for running symfexit locally is to use [`uv`](https://docs.astral.sh/uv/)

Of course, you can use other tools for working with Python, but the instructions below are for `uv`.

1. Install uv following their instructions: https://docs.astral.sh/uv/getting-started/installation/
2. Clone the repository: `git clone https://github.com/roodjong/symfexit.git`
3. Change into the repository: `cd symfexit`
4. Run `uv sync --python 3.13` to install the dependencies. `uv` will also install Python 3.13 for you. A virtual environment will be created at `.venv`.
5. Source the virtual environment: `source .venv/bin/activate` (this differs per shell, for example for fish it is `source .venv/bin/activate.fish`)

You now have the Python environment set up.
You also need a local database.
Use your preferred way to install PostgreSQL, only version 17 is currently recommended, as symfexit is known to work with it.

Usually PostgreSQL is set up to trust your local unix user, so you can create the database and user like this:

```bash
createdb symfexit
```

If you have different users for PostgreSQL, you can set the `DATABASE_URL` environment variable to the correct value.
The default value is `postgres:///symfexit`.

The last step you need to do is to build the theme.

## Running for the first time

If you're running for the first time, the order of the steps is somewhat important.

1. First you need to install the [python dependencies](#dependencies).
2. Then you should set up the database, including the migrations, see below.
3. Then you install the frontend dependencies and [build the styling](#frontend-dependencies).
4. Finally you can run the webserver and worker, see [Run webserver](#run-webserver).

You have to make sure you have postgresql installed and running.
The default [settings.py](symfexit/root/settings.py) file is configured to use a database named `symfexit` with the current (unix) user.

You can change many of the settings using environment variables.
Read the [settings.py](symfexit/root/settings.py) file to see which settings are configurable that way.

If you want to use the default settings on your local machine run these commands after you started postgresql:

```bash
# On linux, you may have to prefix these with sudo -u postgres
createuser $(whoami)
createdb -O $(whoami) symfexit
```

Then you can run the migrations:

```bash
python manage.py migrate
```

To login to the website and admin page, you can create a superuser for yourself:
```
python manage.py createsuperuser
```

## Dependencies

Check that you have at least python 3.12 installed:

```bash
python3 --version
```

Make a virtualenv:

```bash
python3 -m venv ./venv
```

Activate the virtualenv:

```bash
source ./venv/bin/activate
```

Install the dependencies:

```bash
pip install -e .
# Or equivalently:
pip install -r requirements.txt
# Or, if you have uv installed:
uv sync
```

## Frontend dependencies

Then for the styling you also need javascript dependencies (for tailwind):

```bash
cd src/theme/static_src
npm install
```

Build the styling once:

```bash
npm run build
```

Or run the watcher to build the styling every time you save a file, this is useful if you're working on the html templates and adding new classes, as new classes will need to be compiled into the css file:

```bash
npm run dev
```

## Run webserver

```bash
python manage.py runserver
```

The default port is 8000, so you will be able to visit the site at: http://localhost:8000
The admin site is at: http://localhost:8000/admin

## Run worker

```bash
python manage.py startworker
```
