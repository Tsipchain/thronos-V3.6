# Thronos Ecosystem Master Closure 2026

Evidence snapshot: 2026-11-18. Repository state, executable tests, and current
GitHub PR metadata take precedence over older roadmap completion labels.

## Scope and immutable boundaries

This inventory is read-only with respect to production. No merge, deployment,
paid campaign approval, BTC delivery, signer activation, withdrawal activation,
or production balance mutation is authorized by this document.

Reference revisions inspected:

| Repository | Current main revision |
|---|---|
| `Tsipchain/thronos-V3.6` | `1ab95dbc807c653d7e0f2658b5a66aa82b6ecf9b` |
| `Tsipchain/train2earnsystemthronoslasbs` | `98ae0487c77616b6d0d7dbe51fcf23b5c6b35cba` |
| `Tsipchain/thronos-btc-api-adapter` | `4e8ee630314806dd8b801b9b3f90f89310d0d568` |
| `Tsipchain/thronos-basketball-market` | `cd30b07be4e462060b375e0ea9f32c491662ae56` |

## Current-state matrix

Status vocabulary: **VERIFIED**, **IMPLEMENTED / NOT LIVE-VERIFIED**,
**PARTIAL**, **BLOCKED**, **DEPRECATED / DUPLICATE**, and **MISSING**.

| Capability | Status | Canonical implementation and evidence | Closure gate |
|---|---|---|---|
| Persistent Earn accounts and sessions | VERIFIED | `services/earn_account.py`; Earn account regression group | Production session/cookie/domain verification remains operational evidence |
| CPX identity, signed callback and receipt idempotency | IMPLEMENTED / NOT LIVE-VERIFIED | `record_cpx_receipt`, CPX signature/IP gates, pending-to-cleared ledger in `services/earn_account.py` | Controlled provider callback and reversal evidence without fabricated activity |
| TimeWall signed callback, zero milestone, receipt and reversal | IMPLEMENTED / NOT LIVE-VERIFIED | `record_timewall_receipt`, `record_timewall_zero_milestone`, TimeWall routes and adapter tests | Controlled signed callback, clearance, and reversal evidence |
| THC pending/confirmed/payable/paid/reversed ledger | VERIFIED | `thc_ledger`, transition guards and balance tests | Re-run complete gate on every money-path PR |
| THC available/reserved/spent isolation | VERIFIED WITH ADS GAP | `earn_thc_reservations`, cashout/stake/wallet/ad reservation consumers | Wallet-signed ad funding on current main does not create the same authoritative reservation as walletless funding |
| Earn wallet linking | VERIFIED BACKEND; PARTIAL CLIENT PARITY | Challenge, public-key/address binding, durable link in `services/earn_account.py` | Native entry PR #925 is unstable and still requires release build/device QA |
| Referrals and cleared revenue allocation | BLOCKED REGRESSION | Allocation tables and reversal logic exist; baseline produced 3 failures because referral tests expect `cpx_ext_user_id` in `register()` output | Restore one canonical CPX identity contract; retain cleared-only/reversal behavior |
| Internal redeem | PARTIAL | Account ledger primitives exist | Product rail, eligibility, receipt, and production reconciliation need explicit evidence |
| External BTC cashout | BLOCKED / DEFAULT-OFF | Main has reservation/accounting foundations; #881 is dirty and overlaps the newer observer/adapter stack | Preserve existing $25-equivalent minimum and 8–18% fee policy; independently verified reserve, custody, signer, broadcast, and reconciliation required |
| Earn stake/unstake and approved 0.09% fee | IMPLEMENTED / NOT LIVE-VERIFIED | Earn staking tables, reservation checks and tests in `services/earn_account.py` | Funded reward source, real settlement receipt, and production reconciliation |
| Multi-publisher Ads | PARTIAL / ECONOMIC BLOCKER | PR #948 is merged; publisher auth, placements, proofs, replay keys, treasury and Basketball bootstrap exist | Current main can charge CPC clicks and has inconsistent old activation tests; close with view-only billing and migration hold |
| Basketball publisher | IMPLEMENTED / OPERATOR-DEPENDENT | Canonical placements in Thronos and `app/publisher_api.py` in Basketball; Basketball main contains secret-safe preflight | Railway variables, canonical publisher bootstrap, 7/7 preflight and controlled synthetic conservation test |
| Monthly leaderboard ranking | VERIFIED, PRIZES MISSING | 14/14 leaderboard tests; pseudonymous ranking and `prizes_enabled: false` | Versioned rules, cleared-only final snapshot, funded pool, immutable/idempotent awards and admin settlement |
| Integrated Train2Earn | VERIFIED FOUNDATION | 33/33 tests on current main; `services/train_to_earn.py` and gym eligibility proof | #833/#834 require dependency-aware review; no self-report reward path |
| Standalone Gym SaaS | VERIFIED FOUNDATION | 13/13 tests; tenant isolation, provider-confirmed subscription reconciliation, challenge eligibility and HMAC Earn link | Trainer role/QR scheduling in standalone PR #3; real provider reconciliation and funded reward handoff remain non-live |
| ThronosEdu / L2E | VERIFIED FOUNDATION / PARTIAL PRODUCT | 98/98 with isolated writable `EDU_DB_PATH`; `services/l2e_edu.py` and bridge receiver | Default local `/app/data` is not portable; production Stripe reconciliation, teacher THR settlement, funded L2E and release evidence remain gates |
| Wallet PWA/APK | PARTIAL | Extensive Wallet V1 suites and signed operation boundaries exist | PWA/APK device QA, session persistence, release build, internal redeem and recovery migration evidence |
| BTC observer | DRAFT HARDENING | #952 clean Draft; current main has earlier observer/outbox | Historical checkpoint provenance, gap reconciliation, pruned-history evidence and owner merge/deploy approval |
| Legacy BTC pledge credit | UNSAFE ON MAIN UNTIL DRAFT LANDED | #953 clean Draft makes legacy direct-credit fail closed | Review/merge after #952; no production activation |
| BTC adapter verifier/handoff | DRAFT STACK | Adapter #5 -> #6 -> #7 -> #8, all clean relative to their stacked bases | Persistent volume, trusted Core/archival verifier, restart/replay/conflict evidence, authenticated worker; no credit delivery |
| BTC accounting inbox/custody roles | DRAFT STACK | Thronos #954 is stacked on #953 | Retarget only after dependencies; custody configuration and reconciliation approval |
| Survival M0 | DRAFT / ISOLATED | #945 clean; signed offline envelope only | Keep separate from spend, pledge economics and production transport |

## Executable baseline

The following counts are from current main, not from an open PR branch:

| Gate | Result |
|---|---|
| Earn/CPX/TimeWall/hold/referral/revenue/wallet-link/loyalty | **296 passed, 3 failed** |
| Ads marketplace/production/advertising | **116 passed, 13 failed** |
| Integrated Train2Earn and eligibility proof | **33 passed, 0 failed** |
| Standalone Train2Earn | **13 passed, 0 failed** |
| Monthly leaderboard | **14 passed, 0 failed** |
| ThronosEdu/L2E with isolated writable DB | **98 passed, 0 failed** |
| BTC observer/outbox/pledge-retry/reserve subset | **57 passed, 0 failed** |

The Edu suite initially failed collection because its default database path is
`/app/data/l2e_edu.db`; setting an isolated writable `EDU_DB_PATH` produced the
98/98 result. That is an environment portability finding, not a passed default.

## Draft PR dependency and overlap map

| PR | Current state | Dependency / overlap decision |
|---|---|---|
| Thronos #833 | Draft, clean, base `main` | Review against standalone SaaS before merge; do not duplicate tenant/subscription catalog |
| Thronos #834 | Draft, dirty, base #833 branch | Refresh only after #833 decision; verified challenges/tenant leaderboard overlap standalone main |
| Thronos #870 | Draft, dirty | Overlaps newer Earn reservation and wallet-unlock work; audit and extract only non-superseded behavior |
| Thronos #881 | Draft, dirty | Do not merge blindly; overlaps and predates #952-#954 plus adapter #5-#8 |
| Thronos #925 | Draft, unstable | Native Earn entry only; requires current-main refresh and device/build evidence |
| Thronos #945 | Draft, clean | Independent Survival M0 envelope; no settlement or pledge-flow expansion |
| Thronos #952 | Draft, clean | First BTC hardening review target |
| Thronos #953 | Draft, clean | Review after #952; containment, not replacement settlement |
| Thronos #954 | Draft, clean relative to #953 | Retarget after Thronos and adapter dependencies |
| Thronos #948 | Merged | Canonical Ads baseline; follow-up must be a new focused Draft PR |
| Adapter #5 -> #6 -> #7 -> #8 | Draft, clean stacked chain | Preserve exact order; no squashing into unrelated Thronos work |
| Train2Earn #3 | Draft, clean | Trainer role, QR check-in and schedules; compare with Thronos #833/#834 before consolidation |
| Basketball #165 | Draft, dirty | Visibility tracking predates merged Basketball Ads work; audit for superseded hunks, do not merge wholesale |

Recommended BTC review order remains:

`#952 -> #953 -> adapter #5 -> #6 -> #7 -> #8 -> retarget #954`

## Prioritized closure sequence

1. **P0: Ads view-only accounting and campaign lifecycle.** Current main violates
   the approved click-zero-charge policy. Use a focused Draft PR, preserve
   historical CPC records, hold active CPC contracts for explicit remediation,
   and do not activate paid serving.
2. **P0: Referral regression contract.** Resolve the three failing CPX identity
   tests without exposing provider identifiers or changing referral economics.
3. **P0: BTC Draft review chain.** Review only; no activation until persistence,
   independent verification, custody, signer and reconciliation evidence exists.
4. **P1: Gym consolidation.** Decide canonical ownership between standalone main,
   standalone #3, and Thronos #833/#834 before implementation.
5. **P1: Funded leaderboard award engine.** Owner-supplied prize amounts, winner
   count and published terms are prerequisites; never toggle the existing flag.
6. **P1: ThronosEdu release gates.** Close payment, teacher settlement and funded
   reward evidence without treating checkout or quiz completion as settlement.
7. **P1: Wallet client parity and real-device QA.** Refresh #925 only after the
   backend link/session contract is fixed and tested.

## Central evidence policy

Every subsequent closure PR must state: base/head SHA, changed files, exact test
counts, migrations, rollback, production variables, default-disabled gates,
synthetic conservation ledger where money is modeled, and explicit remaining
operator/legal blockers. No roadmap badge is accepted as production evidence.

