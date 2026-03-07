from django.conf import settings


def tenant_config(request):
    tenant = getattr(request, "tenant", None)
    if tenant:
        return {
            "config": {
                "SITE_TITLE": tenant.site_title,
                "LOGO_IMAGE": tenant.logo_image,
                "MAIN_SITE": tenant.main_site,
                "HOMEPAGE_CURRENT": tenant.homepage_current,
                "PAYMENT_TIERS_JSON": tenant.payment_tiers_json,
            }
        }
    return {"config": {}}
