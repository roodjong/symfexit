from django.conf import settings
from django.utils.functional import SimpleLazyObject

from symfexit.tenants.models import TentantSetting


class TenantConfig:
    def __init__(self, tenant):
        self._tenant = tenant

    def __getattr__(self, key):
        if key.startswith("_"):
            return super().__getattr__(key)
        try:
            if len(settings.SITE_CONFIG[key]) not in (2, 3):
                raise AttributeError(key)
            default = settings.SITE_CONFIG[key][0]
        except KeyError as e:
            raise AttributeError(key) from e
        result = TentantSetting.objects.filter(tenant=self._tenant, key=key).first()
        if result is None:
            result = default
            setattr(self, key, default)
            return result
        return result

    def __setattr__(self, name, value):
        if name.startswith("_"):
            return super().__setattr__(name, value)
        if name not in settings.SITE_CONFIG:
            raise AttributeError(name)
        TentantSetting.objects.update_or_create(
            tenant=self._tenant, key=name, defaults={"value": value}
        )

    def __dir__(self):
        return settings.SITE_CONFIG.keys()


class TenantConfigMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, "tenant"):
            return self.get_response(request)
        config = SimpleLazyObject(lambda: TenantConfig(request.tenant))
        request.config = config
        return self.get_response(request)
