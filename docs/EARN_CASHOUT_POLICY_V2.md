# Earn Cashout Policy V2 — non-executable policy gate

Status: draft, read-only, payout disabled.

`services/earn_cashout_policy_v2.py` evaluates eligibility only. It cannot
reserve or debit THC, convert THC to THR, construct or broadcast Bitcoin
transactions, call a signer, or mark a payout as paid.

## Owner-approved policy represented by the gate

- The minimum is USD-equivalent, never a hard-coded THC exchange rate:
  - USD 100.000000 without a verified persisted THR wallet link;
  - USD 25.000000 with a verified persisted THR wallet link.
- The USD value must come from a trusted, short-lived, identity- and
  amount-bound server quote. Browser-provided prices are not accepted.
- Existing external BTC fees remain bounded at 8%–18%; this draft does not
  change the fee, minimum, reservation, or settlement implementation already
  in `EarnAccountStore`.
- Only a trusted, attested sponsorship grant for the internal BTC route may
  produce a zero user-facing additional fee. A caller flag cannot waive fees,
  and an external BTC payout cannot use the sponsored route.
- THC-to-THR eligibility requires the saved wallet link, an attested Pythia
  quote bound to the exact user, wallet and THC amount, and separate current
  proof that the named Pythia reserve has enough THR liquidity.

Every successful decision still returns `payout_enabled: false` and
`eligible_preflight_only_operator_activation_required`. It is evidence for a
future, separately approved coordinator—not authorization to move funds.

## Activation blockers

Before any production payout can be enabled, a separate reviewed change must
provide all of the following:

1. authoritative production THC/USD quote and attestation verification;
2. durable quote/grant/liquidity evidence storage and replay protection;
3. atomic THC reservation with idempotent recovery;
4. an approved sponsored-internal-BTC eligibility authority and sponsor
   accounting ledger;
5. independently verified Pythia reserve liquidity and post-conversion
   reconciliation;
6. isolated BTC payout coordinator, signer policy, node verification and
   uncertain-broadcast recovery;
7. operator-controlled feature gate, staging evidence and explicit owner
   approval.

No existing payout route should consume a V2 preflight result until those
controls are implemented and independently reviewed.
