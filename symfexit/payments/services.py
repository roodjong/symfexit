import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from symfexit.payments.models import (
    Account,
    CancellationReason,
    Payment,
    PaymentObligation,
    PaymentProvider,
    PaymentReversal,
    Transaction,
)

logger = logging.getLogger(__name__)

User = get_user_model()


def reconcile_signup_overpayment_to_user(order, user) -> int:
    """Move any over-payment recorded on a signup order's obligations into the
    new user's credit account.

    During signup the order has no `ordered_for`, so `record_receipt` records
    the full received amount as a Payment against the obligation (because there
    was no user to credit at the time). After the user is created, this walks
    the order's obligations and, for any with negative outstanding (i.e.
    over-paid), creates an adjusting Transaction `debit AR / credit
    user.credit_account` for the surplus.

    Returns the total cents moved to the user's credit account.
    """
    ar_account, _ = Account.get_accounts_receivable_account()
    moved_cents = 0
    for obligation in order.paymentobligation_set.all():
        outstanding = obligation.outstanding_cents
        if outstanding >= 0:
            continue
        surplus = -outstanding
        credit_account = user.get_or_create_credit_account()
        Transaction.objects.create(
            credit_account=credit_account,
            debit_account=ar_account,
            amount_cents=surplus,
        )
        moved_cents += surplus
    return moved_cents


def apply_member_credit(obligation: PaymentObligation) -> Payment | None:
    """Apply any available member credit toward an obligation. Creates a
    credit-funded Payment up to the obligation's outstanding amount.

    Returns the Payment, or None if no credit was applied (no user, no credit
    account, or zero balance / fully-paid obligation).
    """
    user = obligation.order.ordered_for
    if user is None or user.credit_account_id is None:
        return None

    ar_account, _ = Account.get_accounts_receivable_account()
    with transaction.atomic():
        # Lock the user row so concurrent callers (cron + webhook + admin)
        # serialize on the same credit balance and can't both consume it.
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        credit_cents = locked_user.credit_balance_cents
        apply_cents = min(credit_cents, obligation.outstanding_cents)
        if apply_cents <= 0:
            return None

        tx = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=locked_user.credit_account,
            amount_cents=apply_cents,
        )
        # paid_using stays empty: this payment is funded from member credit,
        # not by a payment provider — the provider (e.g. Mollie) has no
        # matching transaction, and labeling it with one is confusing.
        payment = Payment.objects.create(
            obligation=obligation,
            paid_using=None,
            paid_at=timezone.now(),
            transaction=tx,
        )
    return payment


def record_receipt(obligation: PaymentObligation, amount_cents: int) -> Payment | None:
    """Apply a received payment to its obligation; bank any surplus in the
    member's credit account. See `record_receipt_payments`.

    Returns the Payment applied to the obligation, or the surplus Payment if
    the full amount went to credit (because the obligation was already fully
    paid).
    """
    payments = record_receipt_payments(obligation, amount_cents)
    return payments[0] if payments else None


def record_receipt_payments(obligation: PaymentObligation, amount_cents: int) -> list[Payment]:
    """Apply a received payment to its obligation; bank any surplus in the
    member's credit account.

    The surplus is also recorded as a Payment on the obligation, so every
    received amount (e.g. the one-cent bank account change payment on an
    already-paid obligation) stays visible in the admin and the member's
    payment history.

    Returns the Payments it created: the part applied to the obligation and/or
    the surplus, in that order.

    Caller is responsible for idempotency: this function will create a fresh
    Payment + Transaction every time it's called, so processors that may fire
    twice for the same receipt (webhooks, status polls) need their own dedup
    layer around this call.
    """
    order = obligation.order
    user = order.ordered_for
    if order.paid_using and order.paid_using.credit_to_account:
        credit_to_account = order.paid_using.credit_to_account
    else:
        credit_to_account, _ = Account.get_bank_account()

    ar_account, _ = Account.get_accounts_receivable_account()

    with transaction.atomic():
        # Lock the obligation row so concurrent receipts (e.g. two distinct
        # MolliePayments racing, or webhook + manual admin entry) read a
        # consistent `outstanding_cents` and don't double-apply.
        locked_obligation = PaymentObligation.objects.select_for_update().get(pk=obligation.pk)

        if user is not None:
            applied = max(0, min(amount_cents, locked_obligation.outstanding_cents))
            surplus = amount_cents - applied
        else:
            # Signup flow — no user to credit yet. Book the full receipt against
            # the obligation (so its `outstanding_cents` may go negative);
            # `reconcile_signup_overpayment_to_user` later moves the negative
            # balance into the new user's credit account once they're created.
            applied = amount_cents
            surplus = 0
            if amount_cents > locked_obligation.outstanding_cents:
                logger.info(
                    "Signup receipt of %s cents on obligation %s exceeds outstanding by %s; "
                    "surplus will be reconciled to user credit on signup completion",
                    amount_cents,
                    locked_obligation.id,
                    amount_cents - locked_obligation.outstanding_cents,
                )

        payment = None
        surplus_payment = None
        if applied > 0:
            tx = Transaction.objects.create(
                credit_account=ar_account,
                debit_account=credit_to_account,
                amount_cents=applied,
            )
            payment = Payment.objects.create(
                obligation=locked_obligation,
                paid_using=order.paid_using,
                paid_at=timezone.now(),
                transaction=tx,
            )

        if surplus > 0:
            credit_account = user.get_or_create_credit_account()
            surplus_tx = Transaction.objects.create(
                credit_account=credit_account,
                debit_account=credit_to_account,
                amount_cents=surplus,
            )
            surplus_payment = Payment.objects.create(
                obligation=locked_obligation,
                paid_using=order.paid_using,
                paid_at=timezone.now(),
                transaction=surplus_tx,
            )

    return [p for p in (payment, surplus_payment) if p is not None]


def _receipt_account(order):
    """The account `record_receipt` books money received for this order to."""
    if order.paid_using and order.paid_using.credit_to_account:
        return order.paid_using.credit_to_account
    return Account.get_bank_account()[0]


def record_reversal(
    obligation: PaymentObligation,
    payments: list[Payment],
    amount_cents: int,
    reason: PaymentReversal.Reason,
) -> list[PaymentReversal]:
    """Book money that went back to the payer, undoing `payments` in order
    (each up to what is left of it) until `amount_cents` is covered.

    Each reversal is the exact inverse of its payment's transaction: the money
    leaves the account it was received into, and goes back onto the account
    it settled. For the part applied to the obligation that re-opens the
    obligation; for a surplus it takes the money back out of member credit.

    Returns the PaymentReversals. Like `record_receipt`, this is not
    idempotent: callers dedupe upstream.
    """
    order = obligation.order
    user = order.ordered_for

    with transaction.atomic():
        # Same lock as record_receipt, so a reversal and a receipt for one
        # obligation never interleave.
        locked_obligation = PaymentObligation.objects.select_for_update().get(pk=obligation.pk)

        reversals = []
        remaining = amount_cents
        for payment in payments:
            take = min(remaining, payment.unreversed_cents)
            if take <= 0:
                continue
            tx = Transaction.objects.create(
                credit_account_id=payment.transaction.debit_account_id,
                debit_account_id=payment.transaction.credit_account_id,
                amount_cents=take,
            )
            reversals.append(
                PaymentReversal.objects.create(
                    payment=payment,
                    obligation=locked_obligation,
                    transaction=tx,
                    reason=reason,
                )
            )
            remaining -= take

        if remaining > 0:
            # Receipts booked before surpluses got their own Payment: the
            # extra only exists as member credit.
            if user is None:
                raise ValueError(
                    f"Cannot reverse {remaining} cents on obligation {obligation.id}: "
                    "no payment and no member credit to take it from"
                )
            Transaction.objects.create(
                credit_account=_receipt_account(order),
                debit_account=user.get_or_create_credit_account(),
                amount_cents=remaining,
            )

    return reversals


def waive_obligation(obligation: PaymentObligation, max_cents: int | None = None) -> Payment | None:
    """Write off what is still outstanding on an obligation (at most
    `max_cents`), booked as a Payment against the Waived Payments account."""
    ar_account, _ = Account.get_accounts_receivable_account()
    waived_account, _ = Account.get_waived_account()

    with transaction.atomic():
        locked_obligation = PaymentObligation.objects.select_for_update().get(pk=obligation.pk)
        amount_cents = locked_obligation.outstanding_cents
        if max_cents is not None:
            amount_cents = min(amount_cents, max_cents)
        if amount_cents <= 0:
            return None

        tx = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=waived_account,
            amount_cents=amount_cents,
        )
        return Payment.objects.create(
            obligation=locked_obligation,
            paid_using=PaymentProvider.objects.filter(type="waived").first(),
            paid_at=timezone.now(),
            transaction=tx,
        )


def get_refund_option(payment: Payment):
    """Whether `payment` can be refunded online.

    Returns (processor instance, refundable cents), or (None, reason) when it
    can't be.
    """
    provider = payment.paid_using
    processor = provider.get_processor() if provider else None
    if processor is None:
        return None, _("not paid through a payment provider")
    if payment.unreversed_cents <= 0:
        return None, _("already refunded or charged back")
    try:
        instance = processor.get_instance(provider)
    except NotImplementedError:
        instance = None
    cents = instance.refundable_cents(payment) if instance else 0
    if cents <= 0:
        return None, _("can't be refunded online through %(provider)s") % {"provider": provider}
    return instance, cents


def record_refund(
    obligation: PaymentObligation, payments: list[Payment], amount_cents: int
) -> list[PaymentReversal]:
    """A refund is our own choice to return the money, so the member no
    longer owes it: reverse the receipt and waive whatever that re-opened."""
    with transaction.atomic():
        reversals = record_reversal(
            obligation, payments, amount_cents, PaymentReversal.Reason.REFUND
        )
        reversed_cents = sum(r.transaction.amount_cents for r in reversals)
        if reversed_cents:
            waive_obligation(obligation, max_cents=reversed_cents)
    return reversals


def record_chargeback(
    obligation: PaymentObligation, payments: list[Payment], amount_cents: int
) -> list[PaymentReversal]:
    """The member pulled the money back. They still owe it, but we stop
    charging them: the subscription is cancelled, and restarting it takes a
    new order with a fresh first payment."""
    with transaction.atomic():
        reversals = record_reversal(
            obligation, payments, amount_cents, PaymentReversal.Reason.CHARGEBACK
        )
        order = obligation.order
        if order.cancelled_at is None:
            order.cancel(reason=CancellationReason.CHARGEBACK)
    return reversals
