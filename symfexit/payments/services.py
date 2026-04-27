import logging

from django.db import transaction
from django.utils import timezone

from symfexit.payments.models import Account, Payment, PaymentObligation, Transaction

logger = logging.getLogger(__name__)


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
    credit_cents = user.credit_balance_cents
    apply_cents = min(credit_cents, obligation.outstanding_cents)
    if apply_cents <= 0:
        return None

    ar_account, _ = Account.get_accounts_receivable_account()
    with transaction.atomic():
        tx = Transaction.objects.create(
            credit_account=ar_account,
            debit_account=user.credit_account,
            amount_cents=apply_cents,
        )
        payment = Payment.objects.create(
            order=obligation.order,
            obligation=obligation,
            paid_using=obligation.order.paid_using,
            paid_at=timezone.now(),
            transaction=tx,
        )
    return payment


def record_receipt(obligation: PaymentObligation, amount_cents: int) -> Payment | None:
    """Apply a received payment to its obligation; bank any surplus in the
    member's credit account.

    Returns the created Payment, or None if the full amount went to credit
    (because the obligation was already fully paid).

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

    if user is not None:
        applied = max(0, min(amount_cents, obligation.outstanding_cents))
        surplus = amount_cents - applied
    else:
        # Signup flow — no user to credit. Record the full receipt against the
        # obligation; reconciliation happens when the user is linked.
        if amount_cents > obligation.outstanding_cents:
            logger.warning(
                "Receipt of %s cents on obligation %s with no user to credit",
                amount_cents,
                obligation.id,
            )
        applied = amount_cents
        surplus = 0

    with transaction.atomic():
        payment = None
        if applied > 0:
            tx = Transaction.objects.create(
                credit_account=ar_account,
                debit_account=credit_to_account,
                amount_cents=applied,
            )
            payment = Payment.objects.create(
                order=order,
                obligation=obligation,
                paid_using=order.paid_using,
                paid_at=timezone.now(),
                transaction=tx,
            )

        if surplus > 0:
            credit_account = user.get_or_create_credit_account()
            Transaction.objects.create(
                credit_account=credit_account,
                debit_account=credit_to_account,
                amount_cents=surplus,
            )

    return payment
