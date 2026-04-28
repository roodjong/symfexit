import logging
from decimal import Decimal
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

from symfexit.payments.models import PaymentObligation, hashids
from symfexit.payments.mollie.models import MolliePayment
from symfexit.payments.services import record_receipt

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
        amount_cents = int(Decimal(mollie_data["amount"]["value"]) * 100)
        _record_receipt(mollie_payment, amount_cents)
    # A `canceled` Mollie status only means this checkout attempt was
    # abandoned — the obligation stays outstanding so the user can retry
    # (or `charge_obligations` can re-attempt once a mandate exists).
    # Subscription-level cancellation goes through Order.cancel() in admin.


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


def _record_receipt(mollie_payment: MolliePayment, amount_cents: int) -> None:
    """Idempotency wrapper around payments.services.record_receipt. Locks the
    MolliePayment row so concurrent webhook + status-poll callers serialize."""
    with transaction.atomic():
        mp = MolliePayment.objects.select_for_update().get(pk=mollie_payment.pk)
        if mp.processed_at is not None:
            return
        record_receipt(mp.obligation, amount_cents)
        mp.processed_at = timezone.now()
        mp.save(update_fields=["processed_at"])
