# Verify TimeWall callbacks before reward activation

The production receiver is `/api/earn/timewall/postback`. Keep the existing
placement URL, user-ID macro, shared secret and sender-IP allowlist unchanged.

While `TIMEWALL_POSTBACK_LIVE=0`, an authentic callback can be verified without
writing a receipt, THC ledger entry, clearance event, or payout:

1. Open TimeWall through a signed-in Earn Account. This creates its opaque
   provider identity; a made-up user ID will not pass validation.
2. Use the TimeWall publisher postback tools to send/retry a genuine provider
   callback for this identity to the configured receiver. Do not handcraft a
   production credit or disclose the shared secret.
3. Check Master runtime logs for `[TimeWall preflight] verified_callback` and
   `credit_enabled=false ledger_write=false retry_required=true`. The event
   fingerprint correlates a callback without exposing its identity/signature.
4. A `503 ERROR` response is expected during this preflight. It prevents the
   provider from treating an uncredited reward as successfully delivered.
   The generic error alone does not prove that verification succeeded.
5. Once the real callback is verified and live activation is permitted, enable
   live receipt handling on the Master and retry the same callback through the
   provider. A successful live response is `200 OK`, with exactly one pending
   receipt even if the provider retries again.

Preflight checks the configured sender IP, signature, known Earn identity,
nonempty event reference, and finite positive revenue. It does not mark a
provider payment received or a reward cleared. Neither live activation nor
any payout is performed by this change.

Each Earn history row has a Details button that fetches the caller-owned
receipt, real provider reference, dates, state and recorded audit events.
The subsequent internal Earn policy starts a separate seven-day hold when a
verified receipt reaches Earn. Details show this receipt's own hold and countdown
separately from any stored provider ETA. TimeWall task approval before delivery
to Earn and publisher billing are separate events. See
[Earn hold and loyalty](EARN_INTERNAL_HOLD_AND_LOYALTY.md).

Provider deposits to the system BTC address, treasury reserve funding,
internal BTC ledger transfers and external BTC payouts remain separate
reconciliation steps. They are not implemented or simulated here.
