from django import template

from payments.registry import payments_registry

register = template.Library()

@register.simple_tag(takes_context=True)
def payment_start(context, payable):
    for processor in payments_registry:
        if processor.is_available():
            return processor.render_payment_start(context, payable)
    return "Payments unavailable"
