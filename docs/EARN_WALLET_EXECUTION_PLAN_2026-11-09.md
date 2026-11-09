# Earn and Wallet execution plan — 9 November 2026

This is a delivery order, not a declaration that provider receipts have paid
into treasury or that projected rewards are funded. Every money-moving gate
still needs a real balance, receipt and retry-safe settlement journal.

## Baseline verified from main and linked issues

| Area | Implemented in beta | Remaining release check |
|---|---|---|
| Earn account | Email/password, provider identity, pending/cleared history, optional signed wallet link | Device matrix on installed Android/iOS PWA, APK and web (#823) |
| Offers | CPX and TimeWall paths, signed/idempotent callbacks and same-tab provider navigation after promo (#863) | Real-device return to Earn, duplicate click, reversal and first publisher settlement |
| Leaderboard | Monthly Earn view with pseudonymous user entries | Verify rewards/prizes against separate funded contest ledger (#864) |
| Referrals | Invite link, L1/L2 counts and masked invite list in Earn | Qualified earnings, funding, reversal and payout ledger (#853); current percentages are claims, not credits |
| Stake | Walletless THC principal lock; THR requires linked Wallet | Real wallet signing QA; flex/6m/1y terms and fees; funded Pythia APY and reserve accounting (#853) |
| Ads | House promos; marketplace campaign/escrow scaffold | Verified view proof, country targeting, pricing and billable delivery; paid serving remains closed (#860) |
| Payout | THC ledger and seven-day Earn hold | Provider settlement, reserve, quote, internal THR/BTC and external BTC payout receipts (#864) |
| Wallet V1 | Bound signer and PWA/APK surfaces | Migration identity, miner/pool bindings, swap reconnect and cross-device QA (#542, #507, #607) |

Draft PR #865 snapshots 65% player / 35% platform and a referral cap of five
percentage points **within the platform share** for new TimeWall callbacks.
It preserves existing THC conversion; the quote and actual settlement still
need reconciliation. Existing callbacks need a controlled backfill.

## Delivery order

1. **Finish pilot behavior:** review/merge PR #865 after CI and accounting
   review; validate CPX and TimeWall from installed Earn PWA, web and Wallet
   Earn tab. One offer opens in one tab, returns to Earn, and creates one
   verified receipt. Check publisher-approved versus seven-day Earn hold and
   negative/reversal cases. Collect sanitized device evidence for #823.
2. **Reconcile money:** match one Goblins Wood completion to the publisher
   transaction, approved amount, reversal status and actual treasury receipt.
   Version the THC quote and handle old receipts; do not use offer name alone
   as eligibility proof. Confirm actual funds before any prize or payout (#864).
3. **Repair Wallet V1 foundations:** verify legacy-to-V1 identity and protect
   system wallets (#542), preserve mining/Pythia operational bindings (#507),
   and close the reconnect/restore swap failure (#607). Verify PIN/biometric
   approval before THR stake and unstake on PWA/APK/extension.
4. **Fund staking:** distinguish locked principal, projected reward, accrued
   funded reward and paid reward. Define flex/6-month/1-year fees and exit
   rules, signed APY quote and reserve coverage before enabling Pythia payout.
   Walletless THC remains eligible without a wallet booster (#853).
5. **Pay referrals and prizes:** apply eligible L1/L2 rates within the funded
   five-point TimeWall budget, track pending/cleared/reversed/paid per person,
   and display them in Earn. Publish Goblins Wood competition only after its
   three prizes are reserved from actual funds and terms are fixed (#853, #864).
6. **Enable cash-out:** independent signed intent and quote for linked-wallet
   THR, internal BTC and external BTC. Require cleared THC, real reserve,
   idempotency, transaction reference and reconciled completion. External BTC
   uses the agreed $25 equivalent minimum and an approved 8–18% fee schedule
   once tiers are configured (#864).
7. **Open paid ads:** implement server-verified view and country evidence,
   approved THC price packs, capped escrow debit and advertiser reporting;
   keep all Wallet PWA/APK/extension surfaces ad-free (#860).

## Parallel work boundaries

- **Earn accounting owner:** provider receipts, 65/35 quotes, reversals,
  reconciliation, referral and payout ledgers. Never treat pending revenue as
  received BTC or mint an unfunded reward.
- **Wallet owner:** Wallet V1 identity/signing, migration continuity,
  transaction approvals and device QA. No changes to Earn percentages.
- **Publisher/ads owner:** country and view proof, campaign purchase, reporting
  and basketball placements. No billing from browser counters.

The original [Earn roadmap](THRONOS_EARN_ROADMAP.md) remains the release gate
for money movement. Follow #823, #853, #860 and #864 for acceptance evidence.
