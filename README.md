# symfexit

Departure from our old symfony internal site

## Dependencies

Check that you have at least python 3.10 installed:

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

## Run webserver

```bash
python src/manage.py runserver
```

## Run worker

```bash
python src/manage.py startworker
```
