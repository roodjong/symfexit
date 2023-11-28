from django.template import RequestContext, Template
from django.template.loader import get_template
from payments import PaymentProcessor
from payments.models import Payable
from payments.registry import payments_registry
from payments_dummy.forms import FakePayForm
from symfexit import settings


@payments_registry.register(name="dummy", priority=0)
class DummyProcessor(PaymentProcessor):
    def initialize(self):
        pass

    def is_available(self):
        return settings.DEBUG == True

    def render_payment_start(self, context: RequestContext, payable: Payable):
        form = FakePayForm()
        t: Template = get_template("payments_dummy/dummy_pay.html")
        c = context.update({"payable": payable, "form": form})
        return t.render(c, request=context['request'])
