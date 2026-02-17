from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone

from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.models import Order, Payment


def initiate_dummy(request, order_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = FakePayForm(request.POST)
    order = get_object_or_404(Order, id=order_id)
    return_url = request.session.get(f"dummy_return_url_{order.id}", "/")
    if form.is_valid():
        if form.cleaned_data["payment_status"] == "paid":
            obligation = order.get_or_create_next_payment_obligation(
                timezone="UTC"
            )
            Payment.objects.create(
                order=order,
                obligation=obligation,
                paid_at=timezone.now(),
            )
        return HttpResponseRedirect(return_url)
    raise ValueError(form.errors)
