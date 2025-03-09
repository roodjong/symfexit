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
4. Run `uv sync --python 3.13 --dev` to install the dependencies. `uv` will also install Python 3.13 for you. A virtual environment will be created at `.venv`.
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


## Starting the server

To start the server, run:

```bash
python manage.py develop
```

If you haven't started the server before, the command will prompt you to run the migrations.
You can do this by running:

```bash
python manage.py migrate
```

This will start the webserver, the worker for the background tasks, and the watcher for Tailwind.

Whenever you make changes to the Python code, the server will automatically reload.
The watcher for Tailwind will also automatically rebuild the CSS.
