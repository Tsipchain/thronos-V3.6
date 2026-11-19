# Gym funded reward settlement design

Status: Draft boundary; preparation only; no ledger credit or payout path.

This change deliberately does not equate a Gym `T2E_ELIGIBILITY_ONLY` amount
with THC. It prepares an auditable plan only after three independent facts are
available:

1. a durable, authenticated Gym eligibility receipt from the #959 inbox;
2. an authoritative, short-lived quote binding the receipt's exact T2E amount
   to a versioned THC amount;
3. an authoritative, purpose-bound THC reservation sufficient for that exact
   amount.

The quote and funding verifiers are trusted interfaces, not browser claims.
Every field is bound to event, Earn user and Gym tenant. Quote and reservation
identifiers are single-use. SQLite `BEGIN IMMEDIATE`, unique constraints and a
content hash make concurrent retries and process restarts deterministic.

The only stored state is `operator_review_required`. Public results always say
`credit_authorized: false` and `payout_enabled: false`. The module imports no
Earn ledger, wallet, conversion, payout, signer or broadcaster.

## Explicitly deferred activation work

- implement and separately audit the authoritative quote service;
- implement reservation verification against the funded Earn ledger;
- define expiration/release and reversal policy;
- build one atomic coordinator for reservation consumption, ledger credit and
  audit append, including crash recovery and compensation;
- require an operator activation flag and reconciliation evidence.

Until all of those controls are independently reviewed, a prepared plan is not
permission to credit THC and cannot be executed by this module.
