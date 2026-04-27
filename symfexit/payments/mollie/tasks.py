from datetime import timedelta

from django.utils import timezone

from symfexit.payments.mollie.models import MolliePayment
from symfexit.payments.mollie.views import _refresh_from_mollie
from symfexit.worker import logger
from symfexit.worker.registry import task_registry

RECONCILE_THRESHOLD = timedelta(minutes=5)


@task_registry.register("reconcile_mollie_payments")
def reconcile_mollie_payments():
    """Pull status from Mollie for any MolliePayment still 'open' past the
    threshold. Catches missed webhooks where the customer paid at Mollie but
    we never heard about it (because delivery failed and they didn't return
    to the pending page)."""
    cutoff = timezone.now() - RECONCILE_THRESHOLD
    stale = (
        MolliePayment.objects.filter(status="open", created_at__lt=cutoff)
        .select_related("obligation__order__paid_using__mollie_settings")
    )

    refreshed = 0
    errors = 0

    for mp in stale.iterator():
        try:
            _refresh_from_mollie(mp)
            refreshed += 1
        except Exception:
            errors += 1
            logger.log(f"MolliePayment {mp.mollie_payment_id}: ERROR")

    logger.log(f"Reconciled {refreshed} mollie payments, {errors} errors")
