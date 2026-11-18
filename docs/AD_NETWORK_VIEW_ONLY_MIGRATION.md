# Ad Network View-Only Billing Migration

This release is code-only and must remain Draft until owner approval. It does
not approve a production campaign, activate paid serving, deploy code, or change
production variables or balances.

## Contract

- New campaigns use `cpm` as a quote unit, but the only billable event is one
  qualifying verified view. The deterministic event cost is `CPM / 1000` THC.
- Clicks remain durable analytics and always record `0.000000` THC.
- Campaign funding is an Earn THC reservation. Walletless and wallet-authorized
  funding use the same reservation ledger. The legacy THR-to-Pythia ad settlement
  adapter is fail-closed because it crosses the THC/THR boundary.
- A paused campaign retains its full unused reservation. Partial escrow refunds
  are closed; cancellation or final completion is the release boundary.
- A view must carry the signed delivery proof plus at least 1,000 ms viewability,
  at least 50% visibility, and an explicitly visible page state. Missing or
  invalid measurements create no event and no charge.
- Every new charged event stores `thronos-view-fixed-v1`.
- Country/region/publisher/demand weights are present only as inactive quote
  metadata with neutral weights. Dynamic geographic pricing is not activated.

## Existing CPC campaigns

No existing CPC contract is silently repriced.

On schema initialization, CPC campaigns in `active`, `paused`, `approved`, or
`funding_required` are moved to `legacy_contract_review`. Their unused THC
reservation remains locked. They are excluded from paid delivery and cannot be
manually reactivated under a view price.

The advertiser must explicitly choose one of these operator-mediated outcomes:

1. cancel the legacy campaign and release only its unused reservation; or
2. accept a separately quoted, newly created view-only campaign.

Historical campaign rows and historical charged delivery events are retained.
Completed historical CPC reporting is not rewritten.

## Pending-review campaign procedure

The management endpoint
`POST /api/earn/ads/campaign/<id>/policy/evaluate` is authenticated with the
existing non-empty `EARN_MGMT_TOKEN`.

1. Call with `{ "apply": false }` to receive only the deterministic decision and
   reason.
2. Review the campaign/creative, placement registration, budget quote, and the
   reported reason.
3. Only after owner approval, call with `{ "apply": true }`. Safe content may
   move to `funding_required`; uncertain content remains `manual_review`; a
   manual rejection remains rejected.
4. Funding still must be fully reserved and an approved creative must exist
   before activation. This release itself does not call the endpoint.

## Rollout gates

Before any deployment:

- back up the Earn SQLite database including WAL state;
- run the migration against a copy and count CPC campaigns by prior and new
  status;
- verify escrow balance equals active ad reservation for every non-final
  campaign;
- update every publisher client to send viewability fields for view events;
- verify Earn, Wallet Earn, Basketball and each partner placement is registered
  to the correct authenticated publisher;
- verify no sensitive wallet transaction/signing placement is registered;
- run a synthetic conservation test: reserve -> click zero -> one view charge ->
  replay zero -> cancellation -> exact unused release;
- keep paid serving disabled until the owner accepts the evidence.

Rollback must restore code and the pre-migration SQLite/WAL backup together.
Do not edit statuses, reservations, escrow entries, treasury entries, or charged
events manually.

