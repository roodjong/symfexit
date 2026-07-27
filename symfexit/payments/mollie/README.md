# Mollie provider

Mollie is the production payment provider: it handles both the interactive
checkout a member goes through the first time, and the unattended recurring
charges that follow. For the module as a whole — the ledger, obligations, and how
providers plug in — see [../README.md](../README.md).

## Two payment shapes

Mollie's own Subscriptions API is deliberately **not** used. The billing schedule
lives in our `PaymentObligation` rows, and Mollie is only ever told "charge this
customer this amount, now". Every charge is therefore a one-off payment, in one of
two shapes:

| Shape | `sequenceType` | Member involved? | Created by |
| --- | --- | --- | --- |
| First payment | `first` | Yes — goes through Mollie checkout | `start_payment_flow` — [payments.py](payments.py) |
| Recurring | `recurring` | No — charged against a saved mandate | `charge_obligation` — [payments.py](payments.py) |

The first payment is what creates the **mandate**: Mollie's standing permission to
debit that bank account again. Without a mandate there is nothing to charge, so
`charge_obligation` returns `False` and the obligation is simply counted as
skipped. This is the single most common reason automatic charging appears to do
nothing.

## Debugging the automatic charge locally

### Setup: exposing your machine with ngrok

Mollie calls your webhook in test mode exactly as it does in production, and it
rejects `localhost`, `127.0.0.1`, and private IPs as webhook targets. So local
testing needs your development server exposed to the internet with
[ngrok](https://ngrok.com/):

1.  **Register an account** at [ngrok.com](https://ngrok.com/).
2.  **Install the ngrok client** using your distribution's package manager or download from [download.ngrok.com/linux](https://download.ngrok.com/linux).
3.  **Authenticate your agent**: Find your authentication token at [dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken) and register it with your client:
    ```bash
    ngrok config add-authtoken <YOUR AUTH TOKEN HERE>
    ```
4.  **Start ngrok**: Expose the local development port:
    ```bash
    ngrok http 8000
    ```
5.  **Configure using the Ngrok URL**: Using the URL shown in the **Forwarding** row of your ngrok output. Set `test_api_key` with your Mollie API key.
6.  **Add the domain to the tenant**: To make this URL work, you need to add the ngrok domain to your tenant. A quick way to do this is to duplicate an existing entry in the `tenants_domain` database table and update the `domain` column with your new ngrok address.
7.  **Access the application**: Open the ngrok URL provided in the **Forwarding** row instead of `localhost:8000`.

`python manage.py develop` already runs the worker that executes the queued tasks,
so nothing extra is needed there.

Two more steps are needed specifically for the *unattended* charge:

8.  **Set `webhook_base_url`** on the Mollie settings in the admin, to the same
    `https://` ngrok origin (origin only — the code appends `/mollie/webhook/`
    itself). The interactive checkout derives its webhook URL from the incoming
    request, but `charge_obligation` runs in a worker where there is no request, so
    this field is its only source. Left blank, Mollie is handed a bare path and
    rejects the charge.
9.  **Give the member a mandate.** Subscribe as the member through the site once
    and complete the checkout in Mollie's test mode. That single payment creates
    both the `MollieCustomer` row and the mandate that recurring charges need.

### Generate, then charge

Obligations come first — you can only charge something that is owed:

```bash
python manage.py generate_obligations
python manage.py charge_obligations
```

`generate_obligations` also takes `--now YYYY-MM-DD` to pretend it is running on
another date, which is how you roll a subscription into its next period without
waiting for it:

```bash
python manage.py generate_obligations --now 2027-07-25
python manage.py charge_obligations --now 2027-07-25
```

### Click the log line to decide the outcome

Watch the console of whichever process ran the task (the worker, or your shell if
you used `RUN_TASKS_SYNC=1`). A successful charge logs:

```
Mollie payment tr_abc123: set its state in test mode at https://www.mollie.com/checkout/test-mode?...
```

That URL is Mollie's `changePaymentState` link, and it is the whole point of this
loop. A recurring payment has **no checkout URL** — the member isn't present, so
there is no page to send them to — and in test mode Mollie hands you this link
instead so you can decide the outcome yourself. Open it and mark the payment paid
or failed. If you marked it paid, you can reuse the same url, to do a charge back.

