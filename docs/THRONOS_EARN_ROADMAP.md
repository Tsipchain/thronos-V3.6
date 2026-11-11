# Thronos Earn — Pilot-to-Release Roadmap

**Status:** controlled beta  
**Last reviewed:** 2026-11-09
**Scope:** Thronos Earn accounts, provider receipts, PWA/APK/web presentation and optional wallet identity linking.

This document is the release source of truth for Earn. It does **not** change THR mining, fees, pledge rules, pool economics, tokenomics or wallet settlement.

## November 2026 implementation checkpoint

The October pilot table below describes the original release gates. Code has
since added TimeWall receipts, a monthly leaderboard, optional walletless THC
staking, THR wallet staking, referral invite views and ad marketplace scaffolding.
These are distinct from funded yield, referral payouts, cash-out and provider
settlement. See [the Earn and Wallet execution plan](EARN_WALLET_EXECUTION_PLAN_2026-11-09.md)
for current delivery order and acceptance checks. Draft PR #865 records a
TimeWall 65/35 allocation and a 5-point referral cap; it does not release funds.

## Product boundaries

- **THC** is the Earn reward ledger unit. It is separate from THR, L2E, pledge accounting, AMM reserves and liquidity positions.
- An Earn Account is email/password first. A Thronos Wallet is optional.
- A wallet link is a one-time, signed proof that associates an existing Earn Account with the active PWA/APK wallet. It is not a transfer, clearance, wallet creation or payout.
- A provider-reported amount is not a settled asset by itself. Only a verified provider receipt may create a pending THC entry.
- Screenshots and provider dashboards are useful pilot evidence, but never a basis for a manual credit.

## Current beta capabilities

| Capability | Status | Rule |
|---|---|---|
| Email/password Earn Account | Pilot-ready | Wallet is not required |
| CPX offerwall | Pilot-ready | Opens top-level; provider eligibility controls survey availability |
| Signed provider postback | Pilot-ready | Creates one idempotent pending ledger entry |
| Available / pending THC API | Pilot-ready | Decimal strings; server ledger is authoritative |
| Activity and history | Pilot-ready | Per-account only; no cross-account visibility |
| PWA Earn activity view | Released | Shows balance, activity and wallet-link state in-app |
| Existing wallet link | Released | User signs a server-issued challenge once |
| TimeWall | Beta postbacks | Pending THC receipt; reconcile provider approval and payout separately |
| BitcoTasks / further providers | Provider-dependent | Verify provider status and reversal before treating rewards as settled |
| Clearing, payout and cash-out | Disabled | Require verified receipts, durable settlement state and real confirmations |
| Wallet unlock using THC | Disabled | Requires separate pledge and settlement specification |
| THC and THR stake principal | Beta path | THC can lock from cleared Earn balance without wallet; THR requires wallet; validate wallet transaction and device flows |
| Staking yield / revenue share | Not ready for funded payout | Projected APY is not a payable reward; reserve, quote, fees, lock terms and risk review are outstanding |

### Stake fee policy (owner decision 2026-11-10)

- New THC Earn positions: 9 bps (0.09%) on stake **in addition to principal**, and 9 bps on unstake **deducted from returned principal**, rounded up to six THC decimals. Display the exact fee and total/net before each confirmation. The fee is recorded once per action and position in the separate `pythia_thc_staking_fee_reserve` internal accounting ledger; it is not a funded APY distribution or a THR/BTC transfer. Legacy THC positions retain their original fee-free unstake terms.
- New THC positions choose `flex`, `six_months`, or `one_year` at creation. Fixed terms mature at the same UTC clock time after six or twelve **calendar** months (month-end capped to the last valid day); no early unstake. Show the estimated date before confirmation and the exact stored date on the receipt. Existing positions migrate to `flex` without retroactive locks. The 9 bps fee is the same for all terms; duration does not create a funded APY bonus. An idempotency retry cannot alter principal, pool, or term.
- THR staking remains paused until the Wallet PWA/APK performs biometric/passkey approval, signs the exact address/pool/principal/fee/expiry/nonce intent locally, and the backend verifies it before an atomic debit and Pythia credit. Do not charge a THR fee or advertise THR staking as active until that settlement path and its tests exist. Existing THR unstake remains fee-free for now.
- These fees do not change the independent slow/fast network send fees or authorize payout of projected staking rewards.

## Mandatory pilot acceptance matrix

All rows must pass before any clearing or payout discussion.

1. **Email-only account**
   - Register, log in and complete a provider flow.
   - A verified postback appears exactly once as `pending`.
   - Balance and history agree on the same account.

2. **Installed Android PWA**
   - Close and reopen after a service-worker update.
   - Earn history & account remains in the PWA.
   - Available, pending and activity are visible and match the API.

3. **Installed iOS PWA**
   - The same flow as Android, including return from a top-level CPX page.
   - Wallet unlock may be required on return; this is expected security behavior.
   - No second Earn account or duplicate receipt is created.

4. **Existing Thronos PWA/APK wallet**
   - User signs the one-time link from Earn.
   - The linked wallet address appears after refresh.
   - The link exposes no private key, seed, password, session token or provider secret.

5. **Account isolation**
   - Log out and sign in as another Earn account.
   - No previous balance, history or wallet link is visible.

Tracked in: #823.

## Provider onboarding gates

Every new provider, including task or video providers, must have all of the following before its card becomes active:

- written provider approval and current integration documentation;
- server-side provider identity mapping; browser input never chooses the reward account;
- authenticated callback/postback or independently verifiable completion receipt;
- idempotent provider event identifier;
- reward amount conversion documented and tested with decimal precision;
- reversal path;
- provider-specific rate limits and fraud controls;
- disabled-by-default feature flag;
- sandbox and pilot evidence before public traffic.

The same gates apply to any later YouTube-task provider. There is no client-side reward button.

## Future Earn modules

### Leaderboards and competitions

A monthly leaderboard is visible in Earn. Prize distribution remains deferred
until there is sufficient verified activity, funded rewards and anti-fraud
controls. Competitions need a separate ledger, explicit terms, eligibility,
one prize source of truth and a reversal/disqualification path. They do not
clear provider rewards early.

### Wallet-holder product benefits

A linked wallet can later receive product-level conveniences, such as faster identity continuity or eligible feature access. It must not receive a hidden or automatic reward multiplier. Any economic benefit requires a separate approved policy, durable accounting and public disclosure.

### THC staking or soft yield

Beta staking can lock principal; displayed APY is projected and is not a
funded, payable reward. Activation of yield or revenue sharing must first define:

- independent cleared-reward ledger;
- funded and reconciled reserve;
- lock/unlock rules and insolvency handling;
- reconciliation, reversals and audit trail;
- legal, tax and consumer-risk review;
- explicit user consent and no yield guarantee.

Pending provider rewards are never stakeable.

## Release gates for money movement

No cash-out, wallet-unlock settlement, pool withdrawal or reward conversion may be enabled until all are true:

1. verified provider receipt and clearance;
2. durable, idempotent settlement record;
3. funded reserve and reconciliation;
4. real transaction broadcast and confirmation;
5. stored transaction reference;
6. retry-safe failure handling;
7. automated and device acceptance tests;
8. explicit founder authorization.

## Documentation integrity

Public material must label beta functionality as beta and targets as targets. Do not publish unsupported TVL, yield, user-count, revenue or settlement claims. A ledger view is not proof of liquidity; a provider dashboard is not proof of funds received.

## Parallel education work

ThronosEdu/L2E remains independent from THC Earn. Education rewards, attendance, certificates and teacher settlement have their own rules and release gates. Linking a learner or teacher wallet must not merge L2E accounting with CPX/THC rewards.
