from functools import wraps

from django.db import connection


class override_config:
    """Test utility to temporarily override tenant config values.

    Usage as decorator:
        @override_config(SITE_TITLE="Test Site")
        def test_something(self):
            ...

    Usage as context manager:
        with override_config(SITE_TITLE="Test Site"):
            ...
    """

    def __init__(self, **kwargs):
        self.options = kwargs
        self.original_config = None

    def __call__(self, test_func):
        @wraps(test_func)
        def inner(*args, **kwargs):
            with self:
                return test_func(*args, **kwargs)

        return inner

    def __enter__(self):
        tenant = connection.tenant
        if tenant is None:
            msg = "No tenant on connection; cannot override_config"
            raise RuntimeError(msg)
        if not hasattr(tenant, "config"):
            tenant.config = {}
        self.original_config = (tenant.config or {}).copy()
        if tenant.config is None:
            tenant.config = {}
        tenant.config.update(self.options)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        tenant = connection.tenant
        tenant.config = self.original_config
        return False
