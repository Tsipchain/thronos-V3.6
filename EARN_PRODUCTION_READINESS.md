# Earn Production Readiness

Snapshot: 2026-11-18, `thronos-V3.6` main
`1ab95dbc807c653d7e0f2658b5a66aa82b6ecf9b`.

## Readiness summary

| Domain | Code readiness | Live readiness | Decision |
|---|---|---|---|
| Account/session | High | Not evidenced in this audit | Keep; verify production cookie/domain/session persistence |
| CPX | High, feature-gated | Not live-verified | Controlled signed callback + reversal required |
| TimeWall | High, feature-gated | Not live-verified | Controlled signed callback + reversal required |
| THC ledger/clearing | High | Production reconciliation not evidenced | Keep immutable transitions; require receipts |
| Wallet linking | High backend | Native parity incomplete | Refresh #925; device QA required |
| Referral allocation | Regression blocked | No-go | Fix 3 failing tests before release |
| Staking | Accounting implemented | Reward funding/settlement not evidenced | Do not market illustrative APY as payable |
| BTC cashout | Default-off / overlapping Drafts | No-go | Existing $25-equivalent minimum and 8–18% policy remain unchanged; complete BTC gates |
| Ads | Economic policy mismatch | No-go for paid serving | View-only focused PR first |
| Leaderboard prizes | Missing award engine | No-go | Funded, versioned, admin-finalized engine required |

## Provider receipt contract

CPX and TimeWall callbacks are authoritative only after their configured
signature/authenticity checks succeed. Acknowledgement stores a receipt and a
pending ledger entry; it must not fabricate a provider event or bypass the
clearance period. Reversals must reference the original receipt and remain
idempotent. Production evidence must include a provider-originated test event,
its exact stored receipt, clearance transition, and a separately controlled
reversal test.

## Balance contract

`available` must exclude pending rewards, active reservations, stakes, fees and
spent amounts. Cashout, staking, ad funding and wallet settlement must serialize
against the same authoritative reservation view. A UI balance or transient
wallet-link flag is never sufficient authority.

## Current release blockers

1. Referral regression: 3 failures caused by a mismatch between the registration
   return contract and tests consuming `cpx_ext_user_id`.
2. Ads current main: CPC click billing remains reachable and 13 legacy
   advertising tests are red.
3. Real BTC payout: independent reserve, custody, signer, broadcast and
   reconciliation are not all approved and live.
4. Native Earn entry: PR #925 is unstable and has no current release/device QA.
5. Production provider and payment evidence was not supplied; code tests are not
   substitutes for real signed receipts.

## Next focused implementation

The first implementation PR should close Ads view-only billing because it is an
active debit-path policy defect and requires no new economic values. Acceptance:

- click always records `0.000000` charge;
- only qualifying signed views consume reserved THC;
- replay/fake view produces no additional debit;
- CPC creation stops;
- historical CPC reports remain readable;
- active CPC contracts are held for explicit advertiser remediation rather than
  silently converted;
- pause keeps the reservation locked;
- completion/cancellation releases only the unused reservation;
- publisher placement isolation and sensitive wallet-screen exclusions remain;
- no deploy, production approval, or paid-serving activation.

The referral regression should follow in a separate PR because its fix has a
different provider-identity/security boundary.

