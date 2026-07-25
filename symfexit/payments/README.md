# Payments Module

The `payments` module handles the association's financial transactions: sellable
products, member subscriptions, recurring billing, and payment-provider
integrations (Mollie, plus a dummy provider for development and a "waived"
book-keeping provider). Every euro that moves is recorded in a built-in
double-entry ledger so the books always balance.

Two design choices are worth knowing up front:

- **Amounts are integer cents.** `Transaction.amount_cents`, `outstanding_cents`,
  `balance_cents()`, etc. are all cents to avoid floating-point rounding.
  `Product.price_euros` is the one human-facing `Decimal`.
- **The ledger is append-only.** `Transaction` primary keys are TigerBeetle-style
  time-ordered UUIDs, and its foreign keys to `Account` use `db_constraint=False`
  with `on_delete=DO_NOTHING`, so historical transactions keep their account IDs
  even if an account is later removed. Corrections are made by booking new
  transactions, never by editing or deleting old ones.

## Models

### Ledger & chart of accounts

- **GeneralLedger** — a top-level ledger grouping (Assets, Liabilities, Revenue,
  …). Has a unique `code` and a `credit_balance` flag.
- **Account** — a specific account within a ledger (Bank, Accounts Receivable,
  Revenue, …). The `credit_balance` flag records whether the account grows on the
  credit side (liabilities, equity, income) or the debit side (assets, expenses),
  so balances display with the right sign.
- **Transaction** — one ledger movement of `amount_cents` from a `credit_account`
  to a `debit_account`. Multiple transactions that form a single journal entry are
  grouped by a shared `part_of` UUID.

Accounts are created lazily by the `Account.get_*_account()` class methods, and
their codes map onto the Dutch **RGS** (Referentie Grootboekschema) standard:

| Account | Code | `credit_balance` | Purpose |
| --- | --- | --- | --- |
| Accounts Receivable | 13011 | debit | Amounts invoiced to members but not yet received |
| Revenue | 82811 | credit | Membership revenue |
| Bank | 10201 | debit | Default destination for received funds |
| Waived Payments | 45661 | debit | Expense account for forgiven obligations |
| Member credit | 16110 | credit | Per-member prepaid/overpaid balance |

Member-credit accounts all share code `16110` (one Account row per member, looked
up via `Member.credit_account`), so a partial `UniqueConstraint` enforces
uniqueness on every *other* code while exempting the shared one.

### Products, subscriptions & orders

- **Product** — a sellable item (`type` is currently only `SUBSCRIPTION`). Holds
  `sku`, `name`, `price_euros`, and an `enabled` flag.
- **Subscription** — the recurring terms of a product: a `period_unit`
  (`day` / `week` / `month` / `year`) and a `period` count (e.g. every `1` month).
- **Order** — a member's purchase of a product. It **snapshots** the product and
  subscription fields at order time (`product_name`, `product_price_euros`,
  `subscription_period_unit`, …) so later product edits don't rewrite history. It
  links to the buyer (`ordered_for`), a `BillingAddress`, and the
  `PaymentProvider` used (`paid_using`). An order can be cancelled
  (`cancelled_at`).
- **BillingAddress** — name, email, and address captured for invoicing.

### Obligations & payments

- **PaymentObligation** — one amount due for one billing period, identified by
  `(order, year, period)` (unique together). Creating it books the receivable
  journal entry and points at that `Transaction`. Its `outstanding_cents` and
  `is_fully_paid` are derived by summing the `Payment`s applied to it.
- **Payment** — one settlement applied to an obligation, backed by its own
  `Transaction`. A single obligation can have several payments (e.g. member credit
  plus a bank receipt).
- **PaymentProvider** — a configured gateway row: `type` (the registry key, e.g.
  `mollie`), a `credit_to_account` (where received funds land — defaults to Bank),
  and `default` / `enabled` flags.

### Mollie provider

- **MollieSettings** — API keys (live/test), `live_mode`, webhook base URL, and a
  payment-description template. One-to-one with a `PaymentProvider`.
- **MollieCustomer** — maps a local user to a Mollie customer ID (needed for
  recurring mandates).
- **MolliePayment** — tracks an individual Mollie payment attempt and its status;
  the webhook dedup layer keys off this before booking a receipt.

## Provider registry

Providers are plugged in through `payments_registry` (see [registry.py](registry.py)).
Each provider subclasses `PaymentProcessor` and registers itself with a name and
priority:

| Provider | Key | Priority | Notes |
| --- | --- | --- | --- |
| Mollie | `mollie` | 100 | Online + recurring; available when an API key is set |
| Dummy | `dummy` | 0 | Development only (`DEBUG` / `SYMFEXIT_ENV=development`) |
| Waived | `waived` | 0 | No online flow; books against the Waived account |

`is_available()` gates whether a processor can serve traffic, `can_install()`
whether it may be offered in this environment, and `get_instance(provider)`
returns a `PaymentProcessorInstance` that drives the actual flow
(`start_payment_flow` for interactive checkout, `charge_obligation` for
unattended recurring charges).

## Ledger flow

All money movement goes through [services.py](services.py) and
`Order.get_or_create_next_payment_obligation`, each of which books a balanced
journal entry:

| Event | Debit | Credit | Effect |
| --- | --- | --- | --- |
| Obligation created | Accounts Receivable | Revenue | Recognise what the member owes |
| Member credit applied (`apply_member_credit`) | Member credit | Accounts Receivable | Draw down prepaid balance to settle the debt |
| Receipt recorded (`record_receipt`) | Bank (or provider's `credit_to_account`) | Accounts Receivable | Money in, debt down |
| Overpayment surplus | Bank | Member credit | Bank the extra as member credit |
| Signup overpayment reconciled | Accounts Receivable | Member credit | Move a signup surplus onto the new user once created |
| Obligation waived | Waived Payments | Accounts Receivable | Write off the debt as an expense |

Concurrency is handled with `select_for_update()` row locks (on the obligation in
`record_receipt`, on the user in `apply_member_credit`) so racing webhooks, cron
runs, and admin actions can't double-apply. `record_receipt` itself is **not**
idempotent — callers that can fire twice for one receipt (e.g. Mollie webhook plus
status poll) must dedupe upstream via `MolliePayment`.

### Signup edge case

During signup an order has no `ordered_for` user yet, so `record_receipt` books
the whole receipt against the obligation (its `outstanding_cents` may go
negative). Once the user is created,
`reconcile_signup_overpayment_to_user` moves any surplus into their new member
credit account.

## Background tasks

Two worker tasks in [tasks.py](tasks.py) keep subscriptions running:

- **`gen_obligations`** — for every active (non-cancelled) subscription order,
  creates the next period's `PaymentObligation`. Period math is timezone-aware and
  uses the tenant's `payments_timezone`.
- **`charge_obligations`** — for every outstanding obligation whose provider
  supports it, calls `charge_obligation()` to attempt an automatic recurring
  charge. It intentionally does not skip obligations that already have a
  credit-funded payment, since those can still have an outstanding remainder.

## Where things happen (developer map)

New to this module? Start with three files: [models.py](models.py) (the data and
the obligation-booking logic), [services.py](services.py) (**all** money movement),
and [registry.py](registry.py) (the provider plug-in system). The tables below
point at the exact call sites.

### Entry points — what kicks the module into action

| Trigger | Where | Effect |
| --- | --- | --- |
| Member starts a subscription (HTTP) | `_start_payment` — [members/views.py](../members/views.py) | Creates the order + first obligation, then starts the payment flow |
| Signup checkout (HTTP) | `member_signup_pay` — [signup/views.py](../signup/views.py); order made in `get_or_create_order` — [signup/models.py](../signup/models.py) | Same, but for a user that doesn't exist yet |
| Mollie webhook (HTTP, provider callback) | `mollie_webhook` — [mollie/views.py](mollie/views.py) | Records the receipt on a successful payment |
| Dummy pay page (dev only) | `initiate_dummy` — [dummy/views.py](dummy/views.py) | Books a fake receipt for local testing |
| `gen_obligations` (worker/cron task) | [tasks.py](tasks.py) | Creates the next period's obligation for every active order |
| `charge_obligations` (worker/cron task) | [tasks.py](tasks.py) | Auto-charges outstanding obligations via saved mandates |
| Admin manual entry | `save_formset` — [admin.py](admin.py) | Lets staff book obligations/payments by hand |

### Where each object is created

- **`Transaction` (a ledger entry)** — created in exactly three places, and each
  one always books a *balanced* debit + credit:
  - [services.py](services.py) — `record_receipt`, `apply_member_credit`,
    `reconcile_signup_overpayment_to_user`. This is the canonical path.
  - `Order.get_or_create_next_payment_obligation` — [models.py](models.py) — the
    AR/Revenue entry booked when an obligation is first created.
  - [admin.py](admin.py) `save_formset` — manual obligation/payment entry.
  - ⚠️ **Don't `Transaction.objects.create(...)` ad-hoc.** Go through
    [services.py](services.py) so both legs balance and the row locks apply.
- **`Order`** — `Order.objects.create_with_obligation` — [models.py](models.py),
  called from `_start_payment` ([members/views.py](../members/views.py)) and
  `get_or_create_order` ([signup/models.py](../signup/models.py)). (`Product.order`
  in [models.py](models.py) is a lower-level helper that makes only the order.)
- **`PaymentObligation`** — only in
  `Order.get_or_create_next_payment_obligation` ([models.py](models.py)).
  Everything else (`create_with_obligation`, `gen_obligations`) funnels through it.
- **`Payment`** — only in [services.py](services.py) (`record_receipt`,
  `apply_member_credit`). Providers never create `Payment`s directly — they call
  `record_receipt`.
- **`PaymentProvider`** — auto-seeded after every migrate by
  `create_default_providers` ([apps.py](apps.py)) for each installable
  processor, or added by hand in the admin.
- **`Account`** — created lazily by the `Account.get_*_account()` methods in
  [models.py](models.py) and by `Member.get_or_create_credit_account`.

### Adding a payment provider

Providers live in their own sub-app under `payments/` (see
[mollie/](mollie/), [dummy/](dummy/), [waived/](waived/) as references). To add one:

1. **Create the sub-app** `payments/<name>/` with a `payments.py`.
2. **Register a processor.** Subclass `PaymentProcessor` and decorate it with
   `@payments_registry.register(name="<name>", priority=N)` (higher priority wins
   in `get_main()`). Implement `is_available()`, `can_install()`, and
   `get_instance(provider)`; optionally `get_default_credit_account()` and
   `get_settings_inline()`.
3. **Implement the flow.** Return a `PaymentProcessorInstance` from
   `get_instance` with `start_payment_flow(request, obligation, return_url)` — and
   `charge_obligation(obligation)` too if it supports recurring charges.
4. **Book money through services.** On a successful payment call
   `record_receipt(obligation, amount_cents)` — never touch the ledger yourself.
   Add your own idempotency around it (see `_record_receipt` in
   [mollie/views.py](mollie/views.py)).
5. **Install it.** Add the app to `INSTALLED_APPS`. On startup `autodiscover()`
   ([apps.py](apps.py)) imports its `payments.py` (registering the
   processor), and the post-migrate hook seeds a `PaymentProvider` row for it.
