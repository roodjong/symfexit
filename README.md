# symfexit

Departure from our old symfony internal site

## Running for the first time

If you're running for the first time, the order of the steps is somewhat important.

1. First you need to install the [python dependencies](#dependencies).
2. Then you should set up the database, including the migrations, see below.
3. Then you install the frontend dependencies and [build the styling](#frontend-dependencies).
4. Finally you can run the webserver and worker, see [Run webserver](#run-webserver).

You have to make sure you have postgresql installed and running.
The default [settings.py](src/symfexit/settings.py) file is configured to use a database named `symfexit` with the current (unix) user.

You can change many of the settings using environment variables.
Read the [settings.py](src/symfexit/settings.py) file to see which settings are configurable that way.

If you want to use the default settings on your local machine run these commands after you started postgresql:

```bash
createuser $(whoami)
createdb -O $(whoami) symfexit
```

Then you can run the migrations:

```bash
python src/manage.py migrate
```

To login to the website and admin page, you can create a superuser for yourself:
```
python src/manage.py createsuperuser
```

## Dependencies

Check that you have at least python 3.11 installed:

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
python src/manage.py runserver
```

The default port is 8000, so you will be able to visit the site at: http://localhost:8000
The admin site is at: http://localhost:8000/admin

## Run worker

```bash
python src/manage.py startworker
```
