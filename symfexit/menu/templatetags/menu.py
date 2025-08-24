from django import template
from django.apps import apps

register = template.Library()


def generate_menu(request):
    menu_items = list()
    for app in apps.get_app_configs():
        if hasattr(app, "menu_items"):
            menu_items += app.menu_items(request)
    return sorted(menu_items, key=lambda x: x["order"])


@register.inclusion_tag("menu.html", takes_context=True)
def render_main_menu(context):
    request = context["request"]
    return {"menu": generate_menu(request), "current_view": request.resolver_match.view_name}


@register.inclusion_tag("menu_lg.html", takes_context=True)
def render_main_menu_lg(context):
    request = context["request"]
    return {"menu": generate_menu(request), "current_view": request.resolver_match.view_name}
