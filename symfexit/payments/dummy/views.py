from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone

from symfexit.payments.dummy.forms import FakePayForm
from symfexit.payments.models import Account, Payment, PaymentObligation, Transaction


def initiate_dummy(request, obligation_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    form = FakePayForm(request.POST)
    obligation = get_object_or_404(PaymentObligation, id=obligation_id)
    return_url = request.session.get(f"dummy_return_url_{obligation.id}", "/")
    if form.is_valid():
        if form.cleaned_data["payment_status"] == "paid":
            ar_account, _ = Account.get_accounts_receivable_account()
            bank_account, _ = Account.get_bank_account()
            transaction = Transaction.objects.create(
                credit_account=ar_account,
                debit_account=bank_account,
                amount_cents=int(obligation.amount_euros * 100),
            )
            Payment.objects.create(
                order=obligation.order,
                obligation=obligation,
                paid_at=timezone.now(),
                transaction=transaction,
            )
        return HttpResponseRedirect(return_url)
    raise ValueError(form.errors)
