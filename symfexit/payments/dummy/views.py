from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.utils import timezone

from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.models import Order


def initiate_dummy(request, order_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = FakePayForm(request.POST)
    order = Order.get_or_404(order_id)
    if form.is_valid():
        order.payment_status = form.cleaned_data["payment_status"]
        if order.payment_status == Order.Status.PAID:
            order.done_at = timezone.now()
        order.save()
        return HttpResponseRedirect(order.return_url)
    raise form.errors
