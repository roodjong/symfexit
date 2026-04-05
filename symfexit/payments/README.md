# Payments

This app implements a basic accounting system, plus a basic ecommerce system with payment processing.

Payment processing is pluggable (see [registry.py](./registry.py)) so that a payment service provider can be chosen to suit the needs of the tenant.

Moving of money is tracked using the `Transaction` model, which moves money between `Account`s.
The accounts in the `Transaction` are described by UUIDs, but metadata can be added using the `Account` model.
