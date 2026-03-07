from django.db import connection

from symfexit.payments.models import Order
from symfexit.worker import logger
from symfexit.worker.registry import task_registry


@task_registry.register("gen_obligations")
def gen_obligations():
    tenant = connection.tenant
    timezone = tenant.payments_time_zone

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
