import zoneinfo
from datetime import date, datetime, time

from django.db import connection

from symfexit.payments.models import Order, PaymentObligation, _tenant_payments_timezone
from symfexit.payments.registry import payments_registry
from symfexit.worker import logger
from symfexit.worker.registry import task_registry


def _normalize_now(now, timezone_name):
    """Make a `now` override tz-aware in the given timezone. Accepts a `date`
    (interpreted as start-of-day) or a `datetime` (made tz-aware if naive)."""
    tz = zoneinfo.ZoneInfo(timezone_name)
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
    elif isinstance(now, date):
        now = datetime.combine(now, time.min, tzinfo=tz)
    return now


@task_registry.register("gen_obligations")
def gen_obligations(now=None):
    """Generate the next payment obligation for every active subscription order.

    `now` is an optional override for "current time" — useful for backdating or
    forward-dating runs. Accepts a `date` (interpreted as start-of-day in the
    tenant's payments timezone) or a `datetime` (made tz-aware in the tenant's
    payments timezone if naive).
    """
    tenant = connection.tenant
    timezone_name = tenant.payments_timezone

    if now is not None:
        now = _normalize_now(now, timezone_name)

    orders = Order.objects.filter(
        subscription__isnull=False,
        cancelled_at__isnull=True,
    )

    created = 0
    errors = 0

    for order in orders.iterator():
        try:
            order.get_or_create_next_payment_obligation(timezone=timezone_name, now=now)
            created += 1
        except Exception as e:
            errors += 1
            logger.log(f"Order {order.id}: ERROR - {e}")

    logger.log(f"Processed {created} orders, {errors} errors")


@task_registry.register("charge_obligations")
def charge_obligations(now=None):
    """Charge every outstanding payment obligation whose period has started.

    `now` is an optional override for "current time" — useful for testing a
    future charge run against pre-generated obligations. Same semantics as
    `gen_obligations`: accepts a `date` or (naive) `datetime`, interpreted in
    the tenant's payments timezone.
    """
    timezone_name = _tenant_payments_timezone()
    if now is None:
        now = datetime.now(tz=zoneinfo.ZoneInfo(timezone_name))
    else:
        now = _normalize_now(now, timezone_name)

    # Note: no payment__isnull=True filter — an obligation can have a credit-funded
    # Payment that still leaves an outstanding amount, which we want to charge here.
    # The processor's charge_obligation must short-circuit on is_fully_paid.
    obligations = PaymentObligation.objects.filter(
        order__paid_using__isnull=False,
        order__ordered_for__isnull=False,
        order__cancelled_at__isnull=True,
    ).select_related(
        "order__paid_using",
        "order__ordered_for",
    )

    charged = 0
    skipped = 0
    errors = 0

    for obligation in obligations.iterator():
        try:
            # Skip obligations for periods that haven't started yet (they can
            # exist when gen_obligations ran with a future `now` override).
            if (obligation.year, obligation.period) > obligation.order._get_current_period(now):
                skipped += 1
                continue

            if obligation.is_fully_paid:
                skipped += 1
                continue

            provider = obligation.order.paid_using
            processor = payments_registry.get(provider.type)
            if processor is None:
                skipped += 1
                continue

            instance = processor.get_instance(provider)
            if instance.charge_obligation(obligation):
                charged += 1
            else:
                skipped += 1
        except Exception:
            errors += 1
            logger.log(f"Obligation {obligation.id}: ERROR")

    logger.log(f"Charged {charged}, skipped {skipped}, errors {errors}")
