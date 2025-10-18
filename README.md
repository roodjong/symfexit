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


#### Python

1. Install uv following their instructions: https://docs.astral.sh/uv/getting-started/installation/
2. Clone the repository: `git clone https://github.com/roodjong/symfexit.git`
3. Change into the repository: `cd symfexit`
4. Run `uv sync --python 3.13 --dev` to install the dependencies. `uv` will also install Python 3.13 for you. A virtual environment will be created at `.venv`.
5. Source the virtual environment: `source .venv/bin/activate` (this differs per shell, for example for fish it is `source .venv/bin/activate.fish`)

You now have the Python environment set up.
You also need a local database.
Use your preferred way to install PostgreSQL, only version 17 is currently recommended, as symfexit is known to work with it.

By default settings.py is configured to connect with your unix user to the database `symfexit`.
If you want to use this setup, you need to have a PostgreSQL user with the same name as your unix user, and a database named `symfexit` owned by that user.

##### MacOS
```bash
brew install postgresql@17
LC_ALL="C" /opt/homebrew/opt/postgresql@17/bin/postgres -D /opt/homebrew/var/postgresql@17
```

If you installed PostgreSQL on MacOS using Homebrew, you already have a user with the same name as your unix user.
In that case you only need to create the database.

You also probably need to install libmagic separately:

```bash
brew install libmagic
```

##### Linux
On Linux, you probably have to prefix the commands with `sudo -u postgres`.
You may also have to start the PostgreSQL service with `sudo systemctl start postgresql`.

```bash
# On linux, you may have to prefix these with sudo -u postgres
createuser $(whoami)
createdb -O $(whoami) symfexit
```

If you have different users for PostgreSQL, you can set the `DATABASE_URL` environment variable to the correct value.
The default value is `postgres:///symfexit`.


#### Theme with Tailwind

You need to have Node.js installed.
The version of Node.js is not very important.
Tailwindcss says it should work with a Node version of 12 or higher, but you can install your distribution's default version as it should probably work.

Then, you can install the dependencies with:

```bash
cd symfexit/theme/static_src
npm install
```


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

## Localization

All strings are currently in English by default, and have localizations to Dutch.
To translate newly added strings, you need to do the following steps:
1. Generate the list of strings to be translated by running:

```bash
python manage.py makemessages -l nl
```

2. Translate the strings in the `django.po` files.
Django tries to guess the translations based on previously translated strings.
These translations are labeled with "fuzzy", and are ignored when compiling.
So after checking and correcting these translations, the "fuzzy" tag should be removed.

3. Compile the translation files:

```bash
python manage.py compilemessages
```

More information can be found on the Django documentation site: https://docs.djangoproject.com/en/dev/topics/i18n/translation/
