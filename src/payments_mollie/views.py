import json
from django.db import transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from payments.models import Payable
from payments_mollie.models import MolliePayment

from payments_mollie.payments import MollieProcessor


# Create your views here.
def initiate_ideal(request, issuer_id, payable_id):
    processor = MollieProcessor.get_instance()
    if processor is None:
        raise Http404("Mollie payments not configured")
    with transaction.atomic():
        payable = Payable.get_or_404(payable_id)
        if payable.payment_status != Payable.Status.INITIAL:
            return HttpResponseBadRequest("Payment already initiated")
        payable.payment_status = Payable.Status.PENDING
        payable.save()
    payment = processor.client.payments.create(
        {
            "method": "ideal",
            "issuer": issuer_id,
            "amount": {
                "value": "{:.02f}".format(payable.price / 100),
                "currency": "EUR",
            },
            "description": payable.description,
            "redirectUrl": request.build_absolute_uri(
                reverse("payments_mollie:return", args=[payable_id])
            ),
            "cancelUrl": request.build_absolute_uri(
                reverse("payments_mollie:cancel", args=[payable_id])
            ),
            "webhookUrl": request.build_absolute_uri(
                reverse("payments_mollie:webhook")
            ),
        }
    )
    MolliePayment.objects.create(
        payable=payable, payment_id=payment["id"], body=payment
    )
    checkout_url = payment["_links"]["checkout"]["href"]
    return HttpResponseRedirect(checkout_url)


def mollie_return(request, payable_id):
    payable = Payable.get_or_404(payable_id)
    return_url = payable.return_url
    return HttpResponseRedirect(return_url)


def mollie_cancel(request, payable_id):
    payable = Payable.get_or_404(payable_id)
    payable.payment_status = Payable.Status.CANCELLED
    payable.save()
    return_url = payable.return_url
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
        payment.payable.payment_status = Payable.Status.PAID
    if updated_payment["status"] == "canceled":
        payment.payable.payment_status = Payable.Status.CANCELLED
    if updated_payment["status"] == "expired":
        payment.payable.payment_status = Payable.Status.EXPIRED
    if updated_payment["status"] == "failed":
        payment.payable.payment_status = Payable.Status.FAILED
    payment.payable.save()
    payment.save()
    return HttpResponse("")
