"""
Django settings for symfexit project.

Generated by 'django-admin startproject' using Django 4.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

import logging
import os
from pathlib import Path

import dj_database_url

from symfexit.utils import enable_if

try:
    import django_browser_reload

    django_browser_reload_enabled = True
except ImportError:
    django_browser_reload_enabled = False

logger = logging.getLogger(__name__)

# Sentinel objects that are distinct from None
_NOT_SET = object()


class Misconfiguration(Exception):
    """Exception that is raised when something is misconfigured in this file."""


# Many of the settings are dependent on the environment we're running in.
# The default environment is development, so the programmer doesn't have to set anything
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")

_environments = {"development", "production", "staging", "testing"}


def setting(*, development, production, staging=_NOT_SET, testing=_NOT_SET):
    """Generate a setting depending on the DJANGO_ENV and the arguments.

    This function is meant for static settings that depend on the DJANGO_ENV. If the
    staging or testing arguments are left to their defaults, they will fall back to
    the production and development settings respectively.
    """
    if DJANGO_ENV == "development" or (DJANGO_ENV == "testing" and testing is _NOT_SET):
        return development
    if DJANGO_ENV == "testing":
        return testing
    if DJANGO_ENV == "production" or (DJANGO_ENV == "staging" and staging is _NOT_SET):
        return production
    if DJANGO_ENV == "staging":
        return staging
    raise Misconfiguration(f"Set DJANGO_ENV to one of: {', '.join(_environments)}")


def setting_from_env(
    name, *, production=_NOT_SET, staging=_NOT_SET, testing=_NOT_SET, development=None
):
    """Generate a setting that's overridable by the process environment.

    This will raise an exception if a default is not set for production. Because we use
    the sentinel value _NOT_SET, you can still set a default of None for production if wanted.

    As with :func:`setting` the staging and testing values will fall back to production
    and development. So if an environment variable is required in production, and no default
    is set for staging, staging will also raise the exception.
    """
    try:
        return os.environ[name]
    except KeyError:
        if DJANGO_ENV == "production" or (
            DJANGO_ENV == "staging" and staging is _NOT_SET
        ):
            if production is _NOT_SET and os.environ.get("MANAGE_PY", "0") == "0":
                # pylint: disable=raise-missing-from
                raise Misconfiguration(
                    f"Environment variable `{name}` must be supplied in production"
                )
            if production is _NOT_SET and os.environ.get("MANAGE_PY", "0") == "1":
                logger.warning(
                    "Ignoring unset %s because we're running a management command", name
                )
                return development
            return production
        if DJANGO_ENV == "staging":
            return staging
        if DJANGO_ENV == "development" or (
            DJANGO_ENV == "testing" and testing is _NOT_SET
        ):
            return development
        if DJANGO_ENV == "testing":
            return testing
        # pylint: disable=raise-missing-from
        raise Misconfiguration(f"DJANGO_ENV set to unsupported value: {DJANGO_ENV}")


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

CONTENT_DIR = setting_from_env("CONTENT_DIR", production=None, development=BASE_DIR)

DJANGO_ENV = os.getenv("DJANGO_ENV", "development")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = setting_from_env(
    "SYMFEXIT_SECRET_KEY",
    development="django-insecure-7b_@jve6sxl8qz4yc+hc@$(+rr_xiq4y46f^-8y%)&v!%sao6+",
)

MOLLIE_API_KEY = setting_from_env("MOLLIE_API_KEY", production=None)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = setting(development=True, production=False, testing=False)

ALLOWED_HOSTS = setting(
    development=["*"], production=os.getenv("ALLOWED_HOSTS", "").split(",")
)

if DEBUG:
    CSRF_TRUSTED_ORIGINS = ["https://*.ngrok-free.app"]
else:
    CSRF_TRUSTED_ORIGINS = []

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Application definition

DOCS_ENABLED = os.getenv("ENABLE_DOCS", True)
HOME_ENABLED = os.getenv("ENABLE_HOME", True)
SIGNUP_ENABLED = os.getenv("ENABLE_SIGNUP", True)
MEMBERSHIP_ENABLED = os.getenv("ENABLE_MEMBERSHIP", True)
THEMING_ENABLED = os.getenv("ENABLE_THEMING", True)

INSTALLED_APPS = (
    [
        "adminsite.apps.MyAdminConfig",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "tailwind",
        "fontawesomefree",
    ]
    + enable_if(django_browser_reload_enabled, ["django_browser_reload"])
    + [
        "constance",
        "constance.backends.database",
        "tinymce",
        # our own apps
        "theme",
        "menu.apps.MenuConfig",
        "members.apps.MembersConfig",
        "worker.apps.WorkerConfig",
        "payments.apps.PaymentsConfig",
        "payments_dummy.apps.PaymentsDummyConfig",
        "payments_mollie.apps.PaymentsMollieConfig",
    ]
    + enable_if(DOCS_ENABLED, ["documents.apps.DocumentsConfig"])
    + enable_if(HOME_ENABLED, ["home.apps.HomeConfig"])
    + enable_if(SIGNUP_ENABLED, ["signup.apps.SignupConfig"])
    + enable_if(MEMBERSHIP_ENABLED, ["membership.apps.MembershipConfig"])
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
] + enable_if(
    django_browser_reload_enabled,
    ["django_browser_reload.middleware.BrowserReloadMiddleware"],
)

ROOT_URLCONF = "symfexit.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "symfexit.context_processors.constance_vars",
                "theme.context.current_theme",
            ],
            "string_if_invalid": ("😱 MISSING VARIABLE %s 😱" if DEBUG else ""),
        },
    },
]

FORM_RENDERER = "django.forms.renderers.DjangoDivFormRenderer"

WSGI_APPLICATION = "symfexit.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Configure using env variable DATABASE_URL
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://localhost/symfexit",
        conn_max_age=600,
        conn_health_checks=True,
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "nl-NL"

TIME_ZONE = "Europe/Amsterdam"

USE_I18N = True

USE_TZ = True

USE_L10N = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = setting_from_env("STATIC_URL", production="static/", development="static/")
STATIC_ROOT = setting_from_env("STATIC_ROOT", production=None)

MEDIA_URL = setting_from_env("MEDIA_URL", production="media/", development="media/")
MEDIA_ROOT = setting_from_env("MEDIA_ROOT", production=CONTENT_DIR / "media", development=CONTENT_DIR / "media")

DYNAMIC_THEME_URL = setting_from_env("DYNAMIC_THEME_URL", production="theme/", development="static/css/dist/")
DYNAMIC_THEME_ROOT = setting_from_env("DYNAMIC_THEME_ROOT", production=CONTENT_DIR / "theme", development=CONTENT_DIR / "theme" / "static" / "css" / "dist")

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INTERNAL_IPS = [
    "127.0.0.1",
]

TAILWIND_APP_NAME = "theme"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "INFO",
        }
    },
}

# Set the user model to our custom user model
# https://docs.djangoproject.com/en/5.0/ref/settings/#std-setting-AUTH_USER_MODEL

AUTH_USER_MODEL = "members.User"

# Constance fields
CONSTANCE_ADDITIONAL_FIELDS = {
    "image_field": [
        "django.forms.FileField",
        {"required": False, "widget": "symfexit.helpers.ClearableFileInputFromStr"},
    ]
}

# https://django-constance.readthedocs.io/en/latest/#configuration
CONSTANCE_CONFIG = {
    "SITE_TITLE": ("Ledensite", "Hoofdtitel van de site"),
    "LOGO_IMAGE": ("", "Org logo", "image_field"),
    "MAIN_SITE": ("https://roodjongeren.nl/", "Hoofdsite van de organisatie"),
    "HOMEPAGE_CURRENT": (0, "Huidige homepage (stel in op de home pages admin)"),
    "PAYMENT_TIERS_JSON": (
        "{}",
        "JSON met betalingstiers (stel in op membership admin)",
    ),
}
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
