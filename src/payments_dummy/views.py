from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render

from payments.models import Payable
from payments_dummy.forms import FakePayForm

# Create your views here.
def initiate_dummy(request, payable_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = FakePayForm(request.POST)
    payable = Payable.get_or_404(payable_id)
    if form.is_valid():
        payable.payment_status = form.cleaned_data["payment_status"]
        payable.save()
        return HttpResponseRedirect(payable.return_url)
    raise form.errors
