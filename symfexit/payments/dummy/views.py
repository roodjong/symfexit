from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.models import PaymentObligation
from symfexit.payments.services import record_receipt


def initiate_dummy(request, obligation_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    obligation = get_object_or_404(PaymentObligation, id=obligation_id)
    form = FakePayForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "payments_dummy/dummy_pay.html",
            {"obligation": obligation, "form": form},
        )
    return_url = request.session.get(f"dummy_return_url_{obligation.id}", "/")
    if form.cleaned_data["payment_status"] == "paid":
        record_receipt(obligation, int(form.cleaned_data["amount_euros"] * 100))
    return HttpResponseRedirect(return_url)
