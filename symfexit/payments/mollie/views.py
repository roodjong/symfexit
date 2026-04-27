import logging
from urllib.parse import urlencode

from django.db import transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt

from symfexit.payments.models import (
    Account,
    Payment,
    PaymentObligation,
    Transaction,
    hashids,
)
from symfexit.payments.mollie.models import MolliePayment

logger = logging.getLogger(__name__)

PENDING_TIMEOUT_SECONDS = 60
PENDING_POLL_INTERVAL_MS = 2000


def _decode_obligation_eid(eid: str) -> int:
    decoded = hashids.decode(eid)
    if not decoded:
        raise Http404
    return decoded[0]


def build_pending_url(request, obligation: PaymentObligation, return_url: str) -> str:
    path = reverse("payments_mollie:pending", args=[obligation.eid])
    return request.build_absolute_uri(f"{path}?{urlencode({'next': return_url})}")


def _safe_return_url(request, return_url: str) -> str:
    if url_has_allowed_host_and_scheme(
        return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_url
    return "/"


def _refresh_from_mollie(mollie_payment: MolliePayment) -> None:
    obligation = mollie_payment.obligation
    mollie_settings = obligation.order.paid_using.mollie_settings
    client = mollie_settings.get_mollie_client()

    mollie_data = client.payments.get(mollie_payment.mollie_payment_id)
    mollie_payment.status = mollie_data["status"]
    mollie_payment.save(update_fields=["status"])

    if mollie_data.is_paid():
        _create_payment_if_needed(obligation)
    elif mollie_payment.status == "canceled" and obligation.order.cancelled_at is None:
        obligation.order.cancel()


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

    _refresh_from_mollie(mollie_payment)
    return HttpResponse("OK", status=200)


def payment_pending(request, obligation_eid):
    _decode_obligation_eid(obligation_eid)
    return_url = _safe_return_url(request, request.GET.get("next", "/"))
    status_url = reverse("payments_mollie:pending_status", args=[obligation_eid])

    return render(
        request,
        "payments_mollie/pending.html",
        {
            "status_url": status_url,
            "return_url": return_url,
            "timeout_seconds": PENDING_TIMEOUT_SECONDS,
            "poll_interval_ms": PENDING_POLL_INTERVAL_MS,
        },
    )


def payment_pending_status(request, obligation_eid):
    obligation_id = _decode_obligation_eid(obligation_eid)
    latest = (
        MolliePayment.objects.filter(obligation_id=obligation_id)
        .select_related("obligation__order__paid_using__mollie_settings")
        .order_by("-created_at")
        .first()
    )

    if latest is None:
        return JsonResponse({"done": False})

    if latest.status == "open":
        try:
            _refresh_from_mollie(latest)
        except Exception:
            logger.exception(
                "Failed to refresh Mollie payment status for %s", latest.mollie_payment_id
            )

    return JsonResponse({"done": latest.status != "open"})


def _create_payment_if_needed(obligation: PaymentObligation):
    with transaction.atomic():
        locked_obligation = PaymentObligation.objects.select_for_update().get(pk=obligation.pk)

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
