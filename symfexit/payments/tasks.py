from django.db import connection

from symfexit.payments.models import Order, PaymentObligation
from symfexit.payments.registry import payments_registry
from symfexit.worker import logger
from symfexit.worker.registry import task_registry


@task_registry.register("gen_obligations")
def gen_obligations():
    tenant = connection.tenant
    timezone = tenant.payments_timezone

    orders = Order.objects.filter(
        subscription__isnull=False,
        cancelled_at__isnull=True,
    )

    created = 0
    errors = 0

    for order in orders.iterator():
        try:
            order.get_or_create_next_payment_obligation(timezone=timezone)
            created += 1
        except Exception as e:
            errors += 1
            logger.log(f"Order {order.id}: ERROR - {e}")

    logger.log(f"Processed {created} orders, {errors} errors")


@task_registry.register("charge_obligations")
def charge_obligations():
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
