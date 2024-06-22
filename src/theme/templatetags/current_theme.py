from django import template

register = template.Library()

@register.inclusion_tag("theme/tags/current_theme_css.html", takes_context=True)
def theme_css_file(context):
    return {
        "css_file": context["current_theme_css_file"],
    }

@register.inclusion_tag("theme/tags/preload_current_theme_css.html", takes_context=True)
def preload_css_file(context):
    return {
        "css_file": context["current_theme_css_file"],
    }
