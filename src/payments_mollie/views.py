import json

from django.db import transaction
from django.http import (Http404, HttpResponse, HttpResponseBadRequest,
                         HttpResponseRedirect)
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from payments.models import Order
from payments_mollie.models import MolliePayment
from payments_mollie.payments import MollieProcessor


def initiate_ideal(request, issuer_id, order_id):
    processor = MollieProcessor.get_instance()
    if processor is None:
        raise Http404("Mollie payments not configured")
    with transaction.atomic():
        order = Order.get_or_404(order_id)
        if order.payment_status != Order.Status.INITIAL:
            return HttpResponseBadRequest("Payment already initiated")
        order.payment_status = Order.Status.PENDING
        order.save()
    payment = processor.client.payments.create(
        {
            "method": "ideal",
            "issuer": issuer_id,
            "amount": {
                "value": "{:.02f}".format(order.price / 100),
                "currency": "EUR",
            },
            "description": order.description,
            "redirectUrl": request.build_absolute_uri(
                reverse("payments_mollie:return", args=[order_id])
            ),
            "cancelUrl": request.build_absolute_uri(
                reverse("payments_mollie:cancel", args=[order_id])
            ),
            "webhookUrl": request.build_absolute_uri(
                reverse("payments_mollie:webhook")
            ),
        }
    )
    MolliePayment.objects.create(
        order=order, payment_id=payment["id"], body=payment
    )
    checkout_url = payment["_links"]["checkout"]["href"]
    return HttpResponseRedirect(checkout_url)


def mollie_return(request, order_id):
    order = Order.get_or_404(order_id)
    return_url = order.return_url
    return HttpResponseRedirect(return_url)


def mollie_cancel(request, order_id):
    order = Order.get_or_404(order_id)
    order.payment_status = Order.Status.CANCELLED
    order.save()
    return_url = order.return_url
    return HttpResponseRedirect(return_url)


@csrf_exempt
def mollie_webhook(request):
    if request.method != "POST":
        raise Http404("Invalid method")
    processor = MollieProcessor.get_instance()
    payment_id = request.POST["id"]
    payment = MolliePayment.objects.get(payment_id=payment_id)
    updated_payment = processor.client.payments.get(payment_id)
    payment.body = updated_payment
    if updated_payment["status"] == "paid":
        payment.order.payment_status = Order.Status.PAID
    if updated_payment["status"] == "canceled":
        payment.order.payment_status = Order.Status.CANCELLED
    if updated_payment["status"] == "expired":
        payment.order.payment_status = Order.Status.EXPIRED
    if updated_payment["status"] == "failed":
        payment.order.payment_status = Order.Status.FAILED
    payment.order.save()
    payment.save()
    return HttpResponse("")
