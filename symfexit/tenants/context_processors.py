from symfexit.tenants.config import config


def config_context(request):
    """Make tenant config available in templates as {{ config }}."""
    return {"config": config}
