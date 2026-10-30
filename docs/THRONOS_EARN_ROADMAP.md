# Thronos Earn — Pilot-to-Release Roadmap

**Status:** controlled beta  
**Last reviewed:** 2026-10-30  
**Scope:** Thronos Earn accounts, provider receipts, PWA/APK/web presentation and optional wallet identity linking.

This document is the release source of truth for Earn. It does **not** change THR mining, fees, pledge rules, pool economics, tokenomics or wallet settlement.

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
| BitcoTasks / further providers | Disabled | No production enablement until provider validation |
| Clearing, payout and cash-out | Disabled | Require verified receipts, durable settlement state and real confirmations |
| Wallet unlock using THC | Disabled | Requires separate pledge and settlement specification |
| THC stake / APY / revenue share | Not designed for release | Requires reserve, legal, accounting and risk approval |

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

These are deferred until there is sufficient organic activity and verified anti-fraud controls. They must use a separate competition ledger, explicit terms, eligibility rules, one prize source of truth and a reversal/disqualification path. They do not clear provider rewards early.

### Wallet-holder product benefits

A linked wallet can later receive product-level conveniences, such as faster identity continuity or eligible feature access. It must not receive a hidden or automatic reward multiplier. Any economic benefit requires a separate approved policy, durable accounting and public disclosure.

### THC staking or soft yield

No staking, APY, revenue share or liquidity promise is active. A future proposal must first define:

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
