import logging

from django.db import transaction
from django.http import HttpResponse, HttpResponseNotAllowed
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from symfexit.payments.models import Account, Payment, PaymentObligation, Transaction
from symfexit.payments.mollie.models import MolliePayment

logger = logging.getLogger(__name__)


@csrf_exempt
def mollie_webhook(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    payment_id = request.POST.get("id")
    if not payment_id:
        return HttpResponse("OK", status=200)

    try:
        mollie_payment = MolliePayment.objects.select_related(
            "obligation__order__paid_using__mollie_settings",
        ).get(mollie_payment_id=payment_id)
    except MolliePayment.DoesNotExist:
        logger.warning("Received webhook for unknown Mollie payment: %s", payment_id)
        return HttpResponse("OK", status=200)

    obligation = mollie_payment.obligation
    mollie_settings = obligation.order.paid_using.mollie_settings
    client = mollie_settings.get_mollie_client()

    mollie_data = client.payments.get(payment_id)
    mollie_payment.status = mollie_data["status"]
    mollie_payment.save(update_fields=["status"])

    if mollie_data.is_paid():
        _create_payment_if_needed(obligation)

    return HttpResponse("OK", status=200)


def _create_payment_if_needed(obligation: PaymentObligation):
    with transaction.atomic():
        locked_obligation = (
            PaymentObligation.objects.select_for_update().get(pk=obligation.pk)
        )

        if Payment.objects.filter(obligation=locked_obligation).exists():
            return

        ar_account, _ = Account.get_accounts_receivable_account()
        credit_to = (
            locked_obligation.order.paid_using.credit_to_account
            if locked_obligation.order.paid_using
            else Account.get_bank_account()[0]
        )

        t = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=credit_to,
            amount_cents=int(locked_obligation.amount_euros * 100),
        )

        Payment.objects.create(
            order=locked_obligation.order,
            obligation=locked_obligation,
            paid_using=locked_obligation.order.paid_using,
            paid_at=timezone.now(),
            transaction=t,
        )
